"""
تست آزمون درس ۲ (شرط رفتن از سطح ۲ به سطح ۳). اجرا: python tests/test_level2_exam.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_PATH"] = "/tmp/test_laahiq_level2_exam.db"
os.environ.setdefault("BOT_TOKEN", "dummy:token")
DB_PATH = os.environ["DATABASE_PATH"]
for suffix in ("", "-wal", "-shm"):
    if os.path.exists(DB_PATH + suffix):
        os.remove(DB_PATH + suffix)

from bot.database.engine import async_session_factory, run_migrations  # noqa: E402
from bot.domain import lessons_data as ld  # noqa: E402
from bot.domain.salawat_data import LEVEL_2_REQUIRED_SALAWAT  # noqa: E402
from bot.services import lesson_service as ls  # noqa: E402
from bot.services.activity_service import OutcomeStatus, process_activity  # noqa: E402
from bot.services.user_service import get_or_create_user  # noqa: E402

SALAWAT = "اللهم عجل لولیک الفرج"
_uid = 5000
_clock = datetime(2026, 1, 1, tzinfo=timezone.utc)


def check(cond: bool, label: str) -> None:
    print(f"[{'OK  ' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(f"TEST FAILED: {label}")


async def act(tg: int):
    global _uid, _clock
    _uid += 1
    _clock += timedelta(hours=3)  # cooldown مانع نشود
    async with async_session_factory() as s:
        async with s.begin():
            return await process_activity(
                s, update_id=_uid, telegram_id=tg, username="u", first_name="U",
                chat_id=-100, raw_text=SALAWAT, now=_clock,
            )


async def main() -> None:
    await run_migrations()
    tg = 777
    # کاربر سطح ۲ با ۲۴/۲۴
    async with async_session_factory() as s:
        async with s.begin():
            u = await get_or_create_user(s, tg, "u", "U")
            u.game_started = True
            u.level, u.level_progress, u.salawat_count = 2, LEVEL_2_REQUIRED_SALAWAT, 40
            u.lesson1_passed = True
            u.last_salawat_at = _clock - timedelta(days=2)

    out = await act(tg)
    check(out.status == OutcomeStatus.EXAM_REQUIRED and out.exam_lesson_no == 2, "۲۴/۲۴ بدون قبولی درس ۲ → EXAM_REQUIRED")
    async with async_session_factory() as s:
        u = await get_or_create_user(s, tg, "u", "U")
        check(u.level == 2 and u.level_progress == LEVEL_2_REQUIRED_SALAWAT, "سطح و پیشرفت دست‌نخورده می‌ماند")

    lesson = ld.LESSON_BY_NUMBER[2]
    check(lesson.available and len(lesson.questions) == ld.EXAM_QUESTION_COUNT, "درس ۲ فعال با ۱۰ سؤال")
    check(all(len(q.options) == 4 and 0 <= q.correct < 4 for q in lesson.questions), "سؤال‌ها معتبر")

    # قبل از «شنیدم» آزمون باز نمی‌شود؛ «شنیدم» تا ۱ دقیقه بعد از باز کردن درس کار نمی‌کند
    async with async_session_factory() as s:
        async with s.begin():
            u = await get_or_create_user(s, tg, "u", "U")
            st = await ls.start_exam(s, u, 2, _clock)
            check(st.result == ls.ExamStartResult.NOT_HEARD, "بدون «شنیدم» آزمون درس ۲ باز نمی‌شود")
            check(ls.confirm_heard(u, _clock, 2)[0] == ls.HeardResult.NOT_STARTED, "بدون باز کردن درس، «شنیدم» رد می‌شود")
            ls.start_listening(u, _clock, 2)
            check(ls.confirm_heard(u, _clock + timedelta(seconds=10), 2)[0] == ls.HeardResult.TOO_EARLY, "قبل از ۱ دقیقه «شنیدم» رد می‌شود")
            check(ls.confirm_heard(u, _clock + timedelta(seconds=61), 2)[0] == ls.HeardResult.OK and u.lesson2_heard and not u.lesson1_heard, "بعد از ۱ دقیقه «شنیدم» ثبت می‌شود (فقط درس ۲)")

    # مردودی
    async with async_session_factory() as s:
        async with s.begin():
            u = await get_or_create_user(s, tg, "u", "U")
            st = await ls.start_exam(s, u, 2, _clock)
            check(st.result == ls.ExamStartResult.OK, "بعد از «شنیدم» آزمون درس ۲ باز می‌شود")
            exam = st.exam
            for _ in lesson.questions:
                cur = ls.current_question(exam)
                wrong = (cur[1].correct + 1) % 4
                o = await ls.submit_answer(s, u, exam.id, cur[0], wrong, _clock)
            check(o.status == ls.AnswerStatus.FINISHED and not o.grade.passed and not u.lesson2_passed, "همه غلط → مردود")
    out = await act(tg)
    check(out.status == OutcomeStatus.EXAM_REQUIRED, "بعد از مردودی هنوز قفل است")

    # قبولی (بعد از cooldown آزمون)
    later = _clock + timedelta(hours=1)
    async with async_session_factory() as s:
        async with s.begin():
            u = await get_or_create_user(s, tg, "u", "U")
            st = await ls.start_exam(s, u, 2, later)
            exam = st.exam
            for _ in lesson.questions:
                cur = ls.current_question(exam)
                o = await ls.submit_answer(s, u, exam.id, cur[0], cur[1].correct, later)
            check(o.grade.passed and u.lesson2_passed, "همه درست → قبول و lesson2_passed")
            again = await ls.start_exam(s, u, 2, later)
            check(again.result == ls.ExamStartResult.ALREADY_PASSED, "آزمون دوباره‌ی قبول‌شده رد می‌شود")

    out = await act(tg)
    check(out.status == OutcomeStatus.SUCCESS and out.level_up_triggered, "بعد از قبولی ذکر بعدی → سطح ۳")
    async with async_session_factory() as s:
        u = await get_or_create_user(s, tg, "u", "U")
        check(u.level == 3 and u.level_progress == 1, "سطح ۳ و پیشرفت ۱")

    # کاربر سطح ۱ نباید آزمون درس ۲ بدهد
    async with async_session_factory() as s:
        async with s.begin():
            u2 = await get_or_create_user(s, 888, "u2", "U2")
            u2.level = 1
            st = await ls.start_exam(s, u2, 2, _clock)
            check(st.result == ls.ExamStartResult.LEVEL_TOO_LOW, "سطح ۱ → درس ۲ بسته است")

    print("ALL OK")


asyncio.run(main())
