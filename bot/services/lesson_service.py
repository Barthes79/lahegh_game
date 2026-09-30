"""
سرویس دروس و آزمون «مسیر انتظار».

- هر کاربر حداکثر یک دور آزمون فعال دارد؛ اگر نیمه‌کاره رها کند، همان دور (با همان ترتیب سؤال‌ها
  و پاسخ‌های قبلی) ادامه پیدا می‌کند تا با بستن/باز کردن آزمون نتوان ترتیب را عوض کرد.
- آخرین سؤال که پاسخ داده شد، دور بسته و نمره‌دهی می‌شود (منطق نمره در domain/lessons_data.py).
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
    ALREADY_PASSED = "already_passed"
    COOLDOWN = "cooldown"
    UNAVAILABLE = "unavailable"


@dataclass
class ExamStartOutcome:
    result: ExamStartResult
    exam: ExamSession | None = None
    retry_after_seconds: int = 0


def is_lesson_passed(user: User, lesson_no: int) -> bool:
    return bool(user.lesson1_passed) if lesson_no == ld.LEVEL_1_REQUIRED_LESSON else False


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
    if is_lesson_passed(user, lesson_no):
        return ExamStartOutcome(ExamStartResult.ALREADY_PASSED)

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
    else:
        user.exam_last_failed_at = now
        retry_after = ld.EXAM_RETRY_COOLDOWN_SECONDS
    await session.flush()
    return AnswerOutcome(AnswerStatus.FINISHED, exam=exam, grade=grade, retry_after_seconds=retry_after)
