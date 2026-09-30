"""
متن‌های پنل «مسیر انتظار» (سطح ۱): نماز اول وقت، دروس و آزمون.
همه‌ی پیام‌ها HTML هستند (ParseMode پیش‌فرض ربات). ساعت‌ها و شماره‌ها با ارقام انگلیسی نمایش داده می‌شوند.
"""
from __future__ import annotations

from datetime import datetime

from bot.domain import lessons_data as ld
from bot.domain import prayer_times as pt
from bot.domain.lessons_data import ExamGrade, Lesson, Question

# ---------------------------------------------------------------------------
# صفحه‌ی اصلی و منوی نماز
# ---------------------------------------------------------------------------

PATH_HOME = (
    "🕰 <b>مسیر انتظار</b>\n\n"
    "اینجا مسیر آماده شدنته؛ با نماز اول وقت نور می‌گیری و با درس‌ها و آزمون‌ها به سطح بعد می‌رسی."
)
PATH_PRAYER_MENU = "🕌 <b>نماز</b>\n\nیکی از بخش‌ها رو انتخاب کن:"

NOT_STARTED_HINT = ""  # قابلیت قفل لو نمی‌رود: کاربرِ شروع‌نکرده پاسخی نمی‌گیرد.


def first_time_page(views, unavailable: bool = False) -> str:
    lines = ["🌅 <b>نماز اول وقت</b>", ""]
    if unavailable or views is None:
        lines.append("⚠️ اوقات شرعی الان در دسترس نیست؛ کمی بعد دوباره امتحان کن.")
        return "\n".join(lines)
    lines.append(
        f"هر دکمه فقط تا {pt.PRAYER_WINDOW_MINUTES} دقیقه بعد از اذان قابل ثبته و هر نماز روزی یک بار نور می‌ده."
    )
    lines.append("")
    for v in views:
        if v.claimed:
            mark = "✅ ثبت شد"
        elif v.state == pt.WindowState.OPEN:
            mark = f"🟢 باز است تا {pt.format_hhmm(pt.window_end(v.adhan_at))}"
        elif v.state == pt.WindowState.BEFORE:
            mark = "🔒 هنوز وقتش نشده"
        else:
            mark = "🔒 امروز گذشت"
        lines.append(f"{v.prayer.emoji} {v.prayer.label}: اذان {pt.format_hhmm(v.adhan_at)} — {mark}")
    return "\n".join(lines)


def prayer_button_label(view) -> str:
    if view.claimed:
        return f"✅ {view.prayer.label}"
    if view.state == pt.WindowState.OPEN:
        return f"🟢 {view.prayer.label}"
    return f"🔒 {view.prayer.label}"


def prayer_open_page(view) -> str:
    return (
        f"{view.prayer.emoji} <b>{view.prayer.label}</b>\n\n"
        f"اذان امروز: {pt.format_hhmm(view.adhan_at)}\n"
        f"فرصت ثبت تا: {pt.format_hhmm(pt.window_end(view.adhan_at))}\n\n"
        "اگه نمازت رو اول وقت خوندی، دکمه‌ی زیر رو بزن:"
    )


def prayer_claim_success(prayer: pt.PrayerDef, noor_reward: int, noor_current: int) -> str:
    return (
        f"✅ <b>{prayer.label} اول وقت ثبت شد.</b>\n\n"
        f"✨ +{noor_reward} نور\n"
        f"💫 نور معنویتت: {noor_current}\n\n"
        "قبول باشه 🤲"
    )


def prayer_locked_toast(prayer: pt.PrayerDef, adhan_at: datetime, state: pt.WindowState) -> str:
    if state == pt.WindowState.BEFORE:
        return f"هنوز وقتش نشده. اذان {prayer.label.replace('نماز ', '')} امروز ساعت {pt.format_hhmm(adhan_at)} است."
    return f"فرصت ثبت {prayer.label} امروز تموم شد (تا {pt.format_hhmm(pt.window_end(adhan_at))} بود)."


PRAYER_ALREADY_CLAIMED = "این نماز رو امروز قبلاً ثبت کردی ✅"
PRAYER_UNAVAILABLE = "اوقات شرعی الان در دسترس نیست؛ کمی بعد دوباره امتحان کن."

# ---------------------------------------------------------------------------
# دروس
# ---------------------------------------------------------------------------


def lessons_page(passed_lesson1: bool) -> str:
    lines = ["📚 <b>دروس</b>", ""]
    lines.append("هر درس یک آزمون داره. درس ۱ باید قبول بشه تا بتونی از سطح ۱ به سطح ۲ بری.")
    if passed_lesson1:
        lines.append("\n✅ درس ۱ رو قبول شدی.")
    return "\n".join(lines)


def lesson_button_label(lesson: Lesson, passed: bool) -> str:
    if not lesson.available:
        return f"🔒 {lesson.title} (به‌زودی)"
    return f"{'✅' if passed else '📖'} {lesson.title}"


LESSON_COMING_SOON = "این درس به‌زودی اضافه می‌شه."


def lesson_page(lesson: Lesson, passed: bool, retry_wait_seconds: int = 0) -> str:
    lines = [f"📖 <b>{lesson.title}</b>", ""]
    if lesson.intro:
        lines.append(lesson.intro)
        lines.append("")
    if passed:
        lines.append("✅ آزمون این درس رو قبول شدی.")
    else:
        lines.append(
            f"📝 آزمون: {ld.EXAM_QUESTION_COUNT} سؤال؛ با حداقل {ld.EXAM_PASS_SCORE} پاسخ درست قبول می‌شی."
        )
        if retry_wait_seconds > 0:
            lines.append(f"⏳ تا آزمون بعدی: {format_wait(retry_wait_seconds)}")
    return "\n".join(lines)


def format_wait(seconds: int) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{secs:02d}"


# ---------------------------------------------------------------------------
# آزمون (در PV)
# ---------------------------------------------------------------------------

EXAM_SENT_TO_PV = "سؤال‌های آزمون برات توی پی‌وی ربات فرستاده شد 📩"
EXAM_NEED_START_PV = "اول باید ربات رو توی پی‌وی استارت کنی، بعد دوباره «آزمون» رو بزن."
EXAM_START_PV_BUTTON = "🤖 استارت ربات در پی‌وی"
EXAM_ALREADY_PASSED = "این آزمون رو قبلاً قبول شدی ✅"
EXAM_STALE = "این سؤال دیگه معتبر نیست."
EXAM_UNAVAILABLE = "آزمون این درس هنوز آماده نیست."


def exam_cooldown_toast(seconds: int) -> str:
    return f"آزمون قبلی رو قبول نشدی؛ بعد از {format_wait(seconds)} دوباره می‌تونی امتحان بدی."


def exam_question(position: int, total: int, question: Question, lesson: Lesson) -> str:
    lines = [f"📝 <b>آزمون {lesson.title}</b> — سؤال {position} از {total}", "", question.text, ""]
    for index, option in enumerate(question.options, start=1):
        lines.append(f"{index}) {option}")
    return "\n".join(lines)


def exam_result(grade: ExamGrade, lesson: Lesson, questions_by_id: dict[int, Question], retry_seconds: int) -> str:
    lines = [
        f"📋 <b>نتیجه‌ی آزمون {lesson.title}</b>",
        "",
        f"✅ درست: {grade.correct_count}",
        f"❌ غلط: {grade.wrong_count}",
    ]
    if grade.wrong_positions:
        lines.append("")
        lines.append("سؤال‌هایی که اشتباه جواب دادی:")
        for position, qid in zip(grade.wrong_positions, grade.wrong_question_ids):
            lines.append(f"• سؤال {position}: {questions_by_id[qid].text}")
    lines.append("")
    if grade.passed:
        lines.append("🎉 <b>قبول شدی!</b>")
        if lesson.number == ld.LEVEL_1_REQUIRED_LESSON:
            lines.append("حالا با یک «اللهم عجل لولیک الفرج» در گروه وارد سطح ۲ می‌شی.")
    else:
        lines.append(f"حداقل {ld.EXAM_PASS_SCORE} پاسخ درست لازم بود.")
        lines.append(f"⏳ بعد از {max(1, retry_seconds // 60)} دقیقه می‌تونی دوباره آزمون بدی.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# پیام گروه وقتی سطح ۱ تمام شده ولی آزمون قبول نشده
# ---------------------------------------------------------------------------

EXAM_REQUIRED_MESSAGE = (
    "⚠️ برای ادامه باید <b>درس ۱ نماز</b> رو در پنل <b>«مسیر انتظار»</b> به پایان برسونی "
    "و آزمونش رو قبول بشی.\nتا اون موقع ذکرت نور نمی‌ده."
)
