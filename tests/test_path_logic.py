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

from bot.domain import cities_data as cd  # noqa: E402
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
check(sorted(order) == list(range(1, lesson.question_count + 1)), "ترتیب تصادفی شامل همه‌ی سؤال‌ها")
by_id = {q.id: q for q in lesson.questions}
perfect = [by_id[i].correct for i in order]
wrong = list(perfect)
for pos in (2,):
    wrong[pos] = (wrong[pos] + 1) % 4
grade = ld.grade_exam(lesson, order, wrong)
check(grade.correct_count == 6 and grade.passed and grade.wrong_positions == (3,), "۶ از ۷: قبول")
wrong[0] = (wrong[0] + 1) % 4
check(not ld.grade_exam(lesson, order, wrong).passed, "۵ از ۷: مردود")
check(ld.EXAM_RETRY_COOLDOWN_SECONDS == 900, "بعد از مردودی ۱۵ دقیقه انتظار")

# ---- شهرها (موقعیت مکانی) ----
check(len({c.key for c in cd.CITIES}) == len(cd.CITIES), "کلید شهرها یکتاست")
check(all(len(c.key) <= 20 and c.key.isascii() and c.key.islower() for c in cd.CITIES), "کلیدها انگلیسی و کوتاه (جا در callback_data)")
check(all(25 < c.latitude < 40 and 44 < c.longitude < 64 for c in cd.CITIES), "مختصات همه‌ی شهرها داخل ایران است")
pages = [cd.cities_on_page(i) for i in range(cd.page_count())]
check(sum(len(p) for p in pages) == len(cd.CITIES) and all(len(p) <= cd.CITIES_PER_PAGE for p in pages), "صفحه‌بندی: هر شهر دقیقاً یک بار")
check(cd.clamp_page(-1) == 0 and cd.clamp_page(999) == cd.page_count() - 1, "صفحه‌ی خارج از محدوده clamp می‌شود")
check(cd.get_city("tehran") is not None and cd.get_city("nope") is None and cd.get_city(None) is None, "get_city")

# ---- درس ۱: فایل صوتی، «شنیدم» و سؤال‌های آزمون ----
lesson1 = ld.LESSON_BY_NUMBER[1]
check(len(lesson1.media) == 1 and lesson1.media[0].kind == "audio" and lesson1.media[0].file_id == ld.LESSON_1_AUDIO_FILE_ID, "درس ۱ یک فایل صوتی با file_id دارد")
check(ld.LISTEN_WAIT_SECONDS == 60, "«شنیدم» یک دقیقه بعد از باز کردن درس قابل کلیک می‌شود")
check(len(lesson1.questions) == 7 and lesson1.pass_score == 6, "۷ سؤال آزمون درس ۱، قبولی با ۶")
check(all(len(q.options) == 4 and 0 <= q.correct < 4 for q in lesson1.questions), "همه‌ی سؤال‌ها چهارگزینه‌ای با گزینه‌ی درست معتبر")
check(len({q.id for q in lesson1.questions}) == 7 and len({q.text for q in lesson1.questions}) == 7, "سؤال‌ها تکراری نیستند")

sys.exit(1 if failures else 0)
