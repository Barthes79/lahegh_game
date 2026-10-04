"""
سرویس دروس و آزمون «مسیر انتظار».

- هر کاربر حداکثر یک دور آزمون فعال دارد؛ اگر نیمه‌کاره رها کند، همان دور (با همان ترتیب سؤال‌ها
  و پاسخ‌های قبلی) ادامه پیدا می‌کند تا با بستن/باز کردن آزمون نتوان ترتیب را عوض کرد.
- آخرین سؤال که پاسخ داده شد، دور بسته و نمره‌دهی می‌شود (منطق نمره در domain/lessons_data.py).
- قبل از آزمون، کاربر باید درس را گوش بدهد: «شنیدم» تا ۱ دقیقه بعد از باز کردن درس قابل کلیک نیست.
- قبولی در آزمون درس ۱ → user.lesson1_passed = True.  مردودی → ۱۵ دقیقه انتظار.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import ExamSession, User
from bot.domain import lessons_data as ld
from bot.domain.cooldown import remaining_seconds


class ExamStartResult(Enum):
    OK = "ok"
    NOT_HEARD = "not_heard"  # هنوز «شنیدم» نزده
    ALREADY_PASSED = "already_passed"
    COOLDOWN = "cooldown"
    UNAVAILABLE = "unavailable"
    LEVEL_TOO_LOW = "level_too_low"  # درس هنوز برای سطح فعلی کاربر باز نشده


@dataclass
class ExamStartOutcome:
    result: ExamStartResult
    exam: ExamSession | None = None
    retry_after_seconds: int = 0


def is_lesson_passed(user: User, lesson_no: int) -> bool:
    if lesson_no == ld.LEVEL_1_REQUIRED_LESSON:
        return bool(user.lesson1_passed)
    if lesson_no == ld.LEVEL_2_REQUIRED_LESSON:
        return bool(user.lesson2_passed)
    return False


def is_lesson_unlocked(user: User, lesson_no: int) -> bool:
    """آیا سطح کاربر برای باز کردن این درس کافی است؟"""
    return (user.level or 0) >= ld.LESSON_MIN_LEVEL.get(lesson_no, 0)


def exam_order(exam: ExamSession) -> list[int]:
    return json.loads(exam.question_order)


def exam_answers(exam: ExamSession) -> list[int]:
    return json.loads(exam.answers)


def current_question(exam: ExamSession) -> tuple[int, ld.Question] | None:
    """(شماره‌ی سؤال از ۱، خود سؤال) یا None اگر همه پاسخ داده شده."""
    lesson = ld.LESSON_BY_NUMBER[exam.lesson_no]
    order, answers = exam_order(exam), exam_answers(exam)
    if len(answers) >= len(order):
        return None
    by_id = {q.id: q for q in lesson.questions}
    return len(answers) + 1, by_id[order[len(answers)]]


class HeardResult(Enum):
    OK = "ok"
    ALREADY = "already"  # قبلاً «شنیدم» زده
    TOO_EARLY = "too_early"  # هنوز ۱ دقیقه نشده
    NOT_STARTED = "not_started"  # درس را باز نکرده (فایل را نگرفته)


def needs_listen(lesson_no: int) -> bool:
    return lesson_no in ld.LISTEN_REQUIRED_LESSONS


def is_heard(user: User, lesson_no: int) -> bool:
    """آیا «شنیدم» زده شده؟ درس‌هایی که شنیدنشان شرط نیست همیشه True‌اند."""
    if lesson_no == 1:
        return bool(user.lesson1_heard)
    if lesson_no == 2:
        return bool(user.lesson2_heard)
    return True


def _listen_started_at(user: User, lesson_no: int) -> datetime | None:
    return user.lesson2_listen_started_at if lesson_no == 2 else user.lesson1_listen_started_at


def start_listening(user: User, now: datetime, lesson_no: int = 1) -> None:
    """هر بار درس باز و فایل فرستاده می‌شود، انتظار ۱ دقیقه‌ای از نو شروع می‌شود (فقط تا قبل از «شنیدم»)."""
    if is_heard(user, lesson_no):
        return
    if lesson_no == 2:
        user.lesson2_listen_started_at = now
    else:
        user.lesson1_listen_started_at = now


def listen_remaining_seconds(user: User, now: datetime, lesson_no: int = 1) -> int:
    """ثانیه‌های باقی‌مانده تا قابل کلیک شدن «شنیدم» (۰ = قابل کلیک)."""
    return remaining_seconds(_listen_started_at(user, lesson_no), ld.LISTEN_WAIT_SECONDS, now)


def confirm_heard(user: User, now: datetime, lesson_no: int = 1) -> tuple[HeardResult, int]:
    """(نتیجه، ثانیه‌ی باقی‌مانده). فقط وقتی OK است «شنیدم» ثبت می‌شود."""
    if is_heard(user, lesson_no):
        return HeardResult.ALREADY, 0
    if _listen_started_at(user, lesson_no) is None:
        return HeardResult.NOT_STARTED, 0
    wait = listen_remaining_seconds(user, now, lesson_no)
    if wait > 0:
        return HeardResult.TOO_EARLY, wait
    if lesson_no == 2:
        user.lesson2_heard = True
    else:
        user.lesson1_heard = True
    return HeardResult.OK, 0


async def get_active_exam(session: AsyncSession, user: User, lesson_no: int) -> ExamSession | None:
    result = await session.execute(
        select(ExamSession)
        .where(
            ExamSession.user_id == user.id,
            ExamSession.lesson_no == lesson_no,
            ExamSession.status == "active",
        )
        .order_by(ExamSession.id.desc())
    )
    return result.scalars().first()


def retry_remaining_seconds(user: User, now: datetime) -> int:
    return remaining_seconds(user.exam_last_failed_at, ld.EXAM_RETRY_COOLDOWN_SECONDS, now)


async def start_exam(
    session: AsyncSession,
    user: User,
    lesson_no: int,
    now: datetime,
    rng: random.Random | None = None,
) -> ExamStartOutcome:
    lesson = ld.LESSON_BY_NUMBER.get(lesson_no)
    if lesson is None or not lesson.available or not lesson.questions:
        return ExamStartOutcome(ExamStartResult.UNAVAILABLE)
    if not is_lesson_unlocked(user, lesson_no):
        return ExamStartOutcome(ExamStartResult.LEVEL_TOO_LOW)
    if is_lesson_passed(user, lesson_no):
        return ExamStartOutcome(ExamStartResult.ALREADY_PASSED)
    if needs_listen(lesson_no) and not is_heard(user, lesson_no):
        return ExamStartOutcome(ExamStartResult.NOT_HEARD)

    active = await get_active_exam(session, user, lesson_no)
    if active is not None:
        return ExamStartOutcome(ExamStartResult.OK, exam=active)

    wait = retry_remaining_seconds(user, now)
    if wait > 0:
        return ExamStartOutcome(ExamStartResult.COOLDOWN, retry_after_seconds=wait)

    exam = ExamSession(
        user_id=user.id,
        lesson_no=lesson_no,
        question_order=json.dumps(ld.shuffled_question_ids(lesson, rng)),
        answers="[]",
        status="active",
        started_at=now,
    )
    session.add(exam)
    await session.flush()
    return ExamStartOutcome(ExamStartResult.OK, exam=exam)


class AnswerStatus(Enum):
    NEXT = "next"
    FINISHED = "finished"
    STALE = "stale"  # دکمه‌ی قدیمی / دوباره‌کلیک / آزمون بسته‌شده


@dataclass
class AnswerOutcome:
    status: AnswerStatus
    exam: ExamSession | None = None
    grade: ld.ExamGrade | None = None
    retry_after_seconds: int = 0


async def submit_answer(
    session: AsyncSession,
    user: User,
    exam_id: int,
    position: int,
    option: int,
    now: datetime,
) -> AnswerOutcome:
    exam = await session.get(ExamSession, exam_id)
    if exam is None or exam.user_id != user.id or exam.status != "active":
        return AnswerOutcome(AnswerStatus.STALE)

    current = current_question(exam)
    if current is None or current[0] != position:
        return AnswerOutcome(AnswerStatus.STALE, exam=exam)
    _, question = current
    if not 0 <= option < len(question.options):
        return AnswerOutcome(AnswerStatus.STALE, exam=exam)

    answers = exam_answers(exam) + [option]
    exam.answers = json.dumps(answers)

    order = exam_order(exam)
    if len(answers) < len(order):
        await session.flush()
        return AnswerOutcome(AnswerStatus.NEXT, exam=exam)

    lesson = ld.LESSON_BY_NUMBER[exam.lesson_no]
    grade = ld.grade_exam(lesson, order, answers)
    exam.status = "finished"
    exam.score = grade.correct_count
    exam.passed = grade.passed
    exam.finished_at = now
    retry_after = 0
    if grade.passed:
        if exam.lesson_no == ld.LEVEL_1_REQUIRED_LESSON:
            user.lesson1_passed = True
        elif exam.lesson_no == ld.LEVEL_2_REQUIRED_LESSON:
            user.lesson2_passed = True
    else:
        user.exam_last_failed_at = now
        retry_after = ld.EXAM_RETRY_COOLDOWN_SECONDS
    await session.flush()
    return AnswerOutcome(AnswerStatus.FINISHED, exam=exam, grade=grade, retry_after_seconds=retry_after)
