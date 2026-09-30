"""
تست منطق خالص «مسیر انتظار» و ذکر جدید (بدون دیتابیس و بدون تلگرام):
    python tests/test_path_logic.py
"""
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.domain import lessons_data as ld  # noqa: E402
from bot.domain import prayer_times as pt  # noqa: E402
from bot.domain import salawat_data as sd  # noqa: E402
from bot.domain.normalization import normalize_text  # noqa: E402

failures = 0


def check(cond: bool, label: str) -> None:
    global failures
    print(("OK   " if cond else "FAIL ") + label)
    failures += not cond


# ---- ذکر اصلی ----
for text in ("اللهم عجل لولیک الفرج", "اللهم عجل لوليك الفرج", "اَللّهُمَّ عَجِّلْ لِوَلِیِّکَ الْفَرَجَ", "اللهم عجّل لولیّک الفرج"):
    check(sd.is_valid_salawat(normalize_text(text)), f"ذکر معتبر: {text}")
for text in ("اللهم صل علی محمد و آل محمد", "اللهم عجل لولیک", "سلام"):
    check(not sd.is_valid_salawat(normalize_text(text)), f"ذکر نامعتبر: {text}")
check(sd.LEVEL_1_REQUIRED_SALAWAT == 5, "سطح ۱ = ۵ ذکر")

# ---- پنجره‌ی نماز اول وقت ----
tz = ZoneInfo("Asia/Tehran")
payload = {"data": {"timings": {"Fajr": "05:07", "Dhuhr": "12:31", "Maghrib": "18:05"}}}
times = pt.parse_adhan_times(payload, date(2026, 9, 30), tz)
check(times is not None and pt.format_hhmm(times["subh"]) == "05:07", "پارس پاسخ Aladhan")
adhan = times["subh"]
check(pt.window_state(adhan, adhan - timedelta(seconds=1)) == pt.WindowState.BEFORE, "قبل از اذان: بسته")
check(pt.window_state(adhan, adhan) == pt.WindowState.OPEN, "لحظه‌ی اذان: باز")
check(pt.window_state(adhan, adhan + timedelta(minutes=29, seconds=59)) == pt.WindowState.OPEN, "۲۹:۵۹ بعد: باز")
check(pt.window_state(adhan, adhan + timedelta(minutes=30)) == pt.WindowState.AFTER, "۳۰ دقیقه بعد: بسته")
check(pt.parse_adhan_times({"data": {"timings": {"Fajr": "05:07"}}}, date(2026, 9, 30), tz) is None, "پاسخ ناقص: None")

# ---- آزمون ----
lesson = ld.LESSON_BY_NUMBER[1]
order = ld.shuffled_question_ids(lesson, random.Random(1))
check(sorted(order) == list(range(1, ld.EXAM_QUESTION_COUNT + 1)), "ترتیب تصادفی شامل همه‌ی سؤال‌ها")
by_id = {q.id: q for q in lesson.questions}
perfect = [by_id[i].correct for i in order]
wrong = list(perfect)
for pos in (2, 7):
    wrong[pos] = (wrong[pos] + 1) % 4
grade = ld.grade_exam(lesson, order, wrong)
check(grade.correct_count == 8 and grade.passed and grade.wrong_positions == (3, 8), "۸ از ۱۰: قبول")
wrong[0] = (wrong[0] + 1) % 4
check(not ld.grade_exam(lesson, order, wrong).passed, "۷ از ۱۰: مردود")
check(ld.EXAM_RETRY_COOLDOWN_SECONDS == 900, "بعد از مردودی ۱۵ دقیقه انتظار")

sys.exit(1 if failures else 0)
