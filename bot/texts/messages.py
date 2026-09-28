"""
تمام متن‌های نمایشی بازی، یک‌جا.

هرجا سند متن دقیق داده (بخش‌های ۲، ۷، ۸، ۹، ۱۶)، همان عیناً استفاده شده.
هرجا سند فقط «باید چه چیزی توضیح داده شود» را گفته ولی متن دقیق نداده
(مثل پیام‌های Milestone، unlock، تسبیح)، این‌ها بر اساس محتوای الزامی سند نوشته شده‌اند
و در گزارش پایانی به‌عنوان «قابل polish» علامت‌گذاری می‌شوند (طبق TODO شماره ۳ سند).
"""

from __future__ import annotations

from html import escape

import jdatetime

from bot.domain import dua_queue as dua_queue_domain
from bot.domain.dhikr_data import DHIKR_LIST, DhikrDefinition
from bot.domain.tasbih_data import TASBIH_MAX_LEVEL, get_upgrade_cost
from bot.utils.persian_format import (
    format_mmss,
    render_progress_bar,
    render_progress_bar_bold,
    to_persian_digits,
)


# ---------------------------------------------------------------------------
# ابزار داخلی نمایش نوار پیشرفت
# ---------------------------------------------------------------------------


def _format_progress_line(
    level_progress: int,
    level_total: int,
) -> str:
    """
    نوار پیشرفت صلوات.

    یک خط خالی قبل از نوار ایجاد می‌کند و با فاصله‌ی دو طرف،
    نوار را در تلگرام به شکل وسط‌چین تقریبی نمایش می‌دهد.
    """
    progress = render_progress_bar(level_progress, level_total)
    return f"        {progress}"


def _format_progress_line_bold(
    level_progress: int,
    level_total: int,
) -> str:
    """
    نسخه Bold نوار پیشرفت برای پیام‌های مهم‌تر مثل اولین صلوات و Milestone.
    """
    progress = render_progress_bar_bold(level_progress, level_total)
    return f"        {progress}"


# ---------------------------------------------------------------------------
# ابزار نمایش تاریخ شمسی
# ---------------------------------------------------------------------------


def format_shamsi_date(date_str: str) -> str:
    """
    تبدیل تاریخ میلادی YYYY-MM-DD به تاریخ شمسی با اعداد فارسی.
    """
    from datetime import datetime

    gregorian_date = datetime.strptime(date_str, "%Y-%m-%d")
    jalali_date = jdatetime.datetime.fromgregorian(datetime=gregorian_date)

    month_names = [
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ]

    result = f"{jalali_date.day} {month_names[jalali_date.month - 1]} {jalali_date.year}"
    return to_persian_digits(result)


# ---------------------------------------------------------------------------
# بخش ۱: شروع بازی
# ---------------------------------------------------------------------------


def first_salawat_registered(
    noor_reward: int,
    noor_current: int,
    level_progress: int,
    level_total: int,
) -> str:
    paragraphs = [
        "🎉 به سطح ۱ رسیدی!",
        "🌱 اولین قدمت رو برداشتی...",
        "🤲 صلواتت ثبت شد 📿 و مسیرت در لاحق شروع شد.",
        "🎉 به سطح ۱ رسیدی!",
        (
            f"💫 +{to_persian_digits(noor_reward)} نور\n"
            f"💫 نور معنویتت: {to_persian_digits(noor_current)}\n"
            f"{render_progress_bar(level_progress, level_total)}"
        ),
        (
            "هر صلوات، تو رو یک قدم به سطح بعد نزدیک‌تر می‌کنه.\n"
            "و با ذکر الحمدلله می‌تونی نور به دست بیاری و مسیرت رو روشن‌تر کنی. ✨"
        ),
        (
            "🌿 راهت رو ادامه بده...\n"
            "قدم بعدی، با یک صلواته."
        ),
    ]
    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# بخش ۹: نمایش فعالیت‌های موفق
# ---------------------------------------------------------------------------


def salawat_success(
    noor_reward: int,
    noor_current: int,
    cooldown_seconds: int,
    closing_line: str | None = None,
    progress_line: str | None = None,
) -> str:
    lines = [
        "📿 صلواتت با موفقیت ثبت شد.",
        f"✨ +{to_persian_digits(noor_reward)} نور",
        f"💫 نور معنویتت رسید به: {to_persian_digits(noor_current)}",
        f"⏳ صلوات بعدی: {format_mmss(cooldown_seconds)}",
    ]

    if progress_line is not None:
        lines.extend([
            progress_line,
            "",
        ])

    if closing_line:
        lines.append(closing_line)

    return "\n".join(lines)


def dhikr_success(
    noor_reward: int,
    noor_current: int,
    cooldown_seconds: int,
    closing_line: str | None = None,
) -> str:
    """پیام موفقیت عادی ذکر."""
    lines = [
        "✨ ذکرت ثبت شد",
        f"✨ +{to_persian_digits(noor_reward)} نور",
        f"💫 نور معنویتت: {to_persian_digits(noor_current)}",
        f"⏳ ذکر بعدی: {format_mmss(cooldown_seconds)}",
    ]

    if closing_line:
        lines.append(closing_line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# توضیح اولین Reaction
# ---------------------------------------------------------------------------


def reaction_first_time_explanation(
    noor_reward: int,
    noor_current: int,
    progress_line: str | None = None,
    activity_kind: str = "salawat",
) -> str:
    is_dhikr = activity_kind == "dhikr"

    activity_name = "ذکرت" if is_dhikr else "صلواتت"
    activity_plural = "ذکرها" if is_dhikr else "صلوات‌ها"

    lines = [
        f"🙏 این ری‌اکشن یعنی {activity_name} با موفقیت ثبت شده و نورش رو دریافت کردی.",
        "",
        f"✨ +{to_persian_digits(noor_reward)} نور",
        f"💫 نور معنویتت: {to_persian_digits(noor_current)}",
    ]

    if progress_line is not None:
        lines.append(progress_line)

    lines.extend([
        "",
        (
            f"برای اینکه پیام‌های ربات باعث شلوغی چت نشه، بعضی وقت‌ها به‌جای پیام کامل فقط همین "
            f"ری‌اکشن 🙏 رو می‌بینی — یعنی {activity_name} درست ثبت شده."
        ),
        "",
        (
            f"برای اینکه نتیجه‌ی این‌جور {activity_plural} رو توی پیوی هم ببینی، باید یک‌بار "
            f"وارد چت خصوصی ربات بشی و یک پیام براش بفرستی."
        ),
    ])

    return "\n".join(lines)


SUCCESS_REACTION_EMOJI = "🙏"


# ---------------------------------------------------------------------------
# نتیجه فعالیت در PV
# ---------------------------------------------------------------------------


def pv_activity_result(
    noor_reward: int,
    noor_current: int,
    progress_line: str | None = None,
    activity_kind: str = "salawat",
) -> str:
    """
    پیام PV نتیجه فعالیت.

    برای صلوات:
        🤲 صلواتت ثبت شد 📿

    برای ذکر:
        ✨ ذکرت ثبت شد

    فقط صلوات نوار پیشرفت دارد.
    """
    if activity_kind == "dhikr":
        lines = [
            "🤲 ذکرت ثبت شد",
            f"✨ +{to_persian_digits(noor_reward)} نور",
            f"💫 نور معنویتت: {to_persian_digits(noor_current)}",
        ]
    else:
        lines = [
            "🤲 صلواتت ثبت شد 📿",
            f"✨ +{to_persian_digits(noor_reward)} نور",
            f"💫 نور معنویتت: {to_persian_digits(noor_current)}",
        ]

    if progress_line is not None:
        lines.append(progress_line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# بخش ۷ و ۸: cooldown
# ---------------------------------------------------------------------------


def salawat_cooldown_message(remaining_seconds: int) -> str:
    return f"⏳ صلوات بعدی: {format_mmss(remaining_seconds)}"


def dhikr_cooldown_message(remaining_seconds: int) -> str:
    return f"⏳ ذکر بعدی: {format_mmss(remaining_seconds)}"


# طبق درخواست صریح کاربر، هیچ پیام هشدار «متن نامعتبر» دیگر وجود ندارد
# و در هیچ حالتی نمایش داده نمی‌شود.


# ---------------------------------------------------------------------------
# بخش ۱۱: Milestoneها
# ---------------------------------------------------------------------------


_MILESTONE_FEATURE_PARAGRAPHS: dict[str, list[str]] = {
    "bank_azkar": [
        "✨ **یک بخش تازه برات باز شد...**",
        "📖 **بانک اذکار**",
        "از اینجا می‌تونی ذکرهای مختلف رو ببینی و با نورت بعضی از اون‌ها رو باز کنی.",
        "💫 هر ذکر، مقدار نور متفاوتی بهت می‌ده.",
        "برای دیدنش بنویس: **«بانک اذکار»**",
    ],
    "nameh_amal": [
        "🌿 **نصف راه سطح ۱ رو رفتی...**",
        "همینطور با آرامش ادامه بده؛ هر صلوات یه قدم دیگه به سمت جلوئه.",
        "📜 **یک بخش تازه هم برات باز شد: نامه اعمالم**",
        "از اینجا می‌تونی مسیرت در «لاحق» رو ببینی؛ از تعداد صلوات و ذکرها گرفته تا نور و فعالیت‌هات.",
        "برای دیدنش بنویس: **«نامه اعمالم»**",
    ],
    "tasbih": [
        "📿 **یک ابزار تازه برای مسیرت باز شد...**",
        "**تسبیح**",
        "با ارتقای تسبیح، زمان انتظار بین ذکرهات کمتر می‌شه.",
        "هرچه تسبیحت رو بالاتر ببری، سریع‌تر می‌تونی ذکرهای بیشتری ثبت کنی. ✨",
        "برای دیدن وضعیت تسبیحت بنویس: **«تسبیح»**",
    ],
    "level_up": [
        "🌟 **مسیر سطح ۱ رو کامل کردی...**",
        "🎉 **تبریک! وارد سطح ۲ شدی.**",
        "✨ نورهایی که به دست آوردی برای خودت باقی می‌مونن.",
        "🌱 این تازه شروع مسیرته...",
    ],
}


def salawat_milestone_message(
    milestone_kind: str,
    noor_reward: int,
    noor_current: int,
    level_progress: int,
    level_total: int,
) -> str:
    feature_paragraphs = _MILESTONE_FEATURE_PARAGRAPHS.get(milestone_kind, [])

    lines = [
        "🤲 صلواتت ثبت شد 📿",
        f"✨ +{to_persian_digits(noor_reward)} نور",
        f"💫 نور معنویتت: {to_persian_digits(noor_current)}",
        render_progress_bar(level_progress, level_total),
        "",
    ]

    lines.extend(feature_paragraphs)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# بخش ۱۳: بانک اذکار
# ---------------------------------------------------------------------------


def bank_azkar_panel_header() -> str:
    return (
        "🗝 **بانک اذکار**\n\n"
        "ذکرهایی که باز کردی نور می‌دن؛ برای بقیه می‌تونی با نور بازشون کنی."
    )


def bank_azkar_entry_button_label(
    dhikr: DhikrDefinition,
    unlocked: bool,
) -> str:
    status = "✅" if unlocked else "🔒"
    return f"{status} {dhikr.display_name} — ✨{to_persian_digits(dhikr.noor_reward)}"


def bank_azkar_detail_unlocked(dhikr: DhikrDefinition) -> str:
    return (
        f"**{dhikr.display_name}**\n\n"
        f"✨ {to_persian_digits(dhikr.noor_reward)} نور در هر بار\n"
        f"✅ باز شده"
    )


def bank_azkar_detail_locked(dhikr: DhikrDefinition) -> str:
    cost = (
        "رایگان"
        if dhikr.unlock_cost == 0
        else f"{to_persian_digits(dhikr.unlock_cost)} نور"
    )

    return (
        f"🔒 **{dhikr.display_name}**\n\n"
        f"✨ {to_persian_digits(dhikr.noor_reward)} نور در هر بار\n"
        f"💫 هزینه باز کردن: {cost}\n\n"
        "می‌خوای این ذکر رو باز کنی؟"
    )


def bank_azkar_purchase_success(dhikr: DhikrDefinition) -> str:
    return (
        f"✅ «{dhikr.display_name}» با موفقیت باز شد!\n"
        "از حالا هر وقت بفرستیش نور می‌گیری."
    )


def bank_azkar_purchase_insufficient(
    dhikr: DhikrDefinition,
    noor_current: int,
) -> str:
    missing = dhikr.unlock_cost - noor_current
    return (
        f"💫 نورت برای باز کردن «{dhikr.display_name}» کافی نیست.\n"
        f"نیاز: {to_persian_digits(dhikr.unlock_cost)} | "
        f"کمبود: {to_persian_digits(missing)}"
    )


BANK_AZKAR_BACK_BUTTON_LABEL = "↩️ بازگشت به بانک اذکار"
BANK_AZKAR_BUY_BUTTON_LABEL = "تایید خرید ✅"

UNLOCK_BUTTON_LABEL = "باز کردن 🔓"


def unlock_confirm_prompt(dhikr: DhikrDefinition) -> str:
    return (
        f"می‌خوای «{dhikr.display_name}» رو با "
        f"{to_persian_digits(dhikr.unlock_cost)} نور باز کنی؟"
    )


def unlock_success(dhikr: DhikrDefinition) -> str:
    return (
        f"✅ «{dhikr.display_name}» با موفقیت باز شد! "
        "از حالا هر وقت بفرستیش نور می‌گیری."
    )


def unlock_insufficient_noor(
    dhikr: DhikrDefinition,
    noor_current: int,
) -> str:
    missing = dhikr.unlock_cost - noor_current
    return (
        f"💫 نورت برای باز کردن «{dhikr.display_name}» کافی نیست.\n"
        f"نور معنویتت: {to_persian_digits(noor_current)} | "
        f"نیاز: {to_persian_digits(dhikr.unlock_cost)} "
        f"(کمبود: {to_persian_digits(missing)})"
    )


UNLOCK_ALREADY_DONE = "این ذکر قبلاً باز شده."

CONFIRM_YES = "تایید ✅"
CONFIRM_NO = "انصراف ❌"


# ---------------------------------------------------------------------------
# بخش ۱۴: نامه اعمالم
# ---------------------------------------------------------------------------


def nameh_amal(
    *,
    start_date_str: str,
    level: int,
    salawat_progress: int,
    salawat_progress_total: int,
    salawat_count: int,
    dhikr_count: int,
    noor_current: int,
    noor_total_earned: int,
    chest_count: int,
    tasbih_level: int,
    tasbih_unlocked: bool,
    dhikr_unlocked_count: int,
    total_activities: int,
    last_activity_str: str,
) -> str:
    lines = [
        "📜 نامه اعمالم\n",
        f"📅 تاریخ شروع پیشرفت معنویت: {start_date_str}",
        f"🎚 سطح فعلی: {to_persian_digits(level)}",
        (
            f"🤲 پیشرفت صلوات: "
            f"{render_progress_bar(salawat_progress, salawat_progress_total)}"
        ),
        f"🤲 تعداد صلوات: {to_persian_digits(salawat_count)}",
        f"✨ تعداد ذکرها: {to_persian_digits(dhikr_count)}",
        f"💫 نور معنویتت: {to_persian_digits(noor_current)}",
        f"🎁 تعداد صندوقچه‌های پیدا شده: {to_persian_digits(chest_count)}",
    ]

    if tasbih_unlocked:
        lines.append(f"📿 سطح فعلی تسبیح: {to_persian_digits(tasbih_level)}")

    lines.append(f"🔓 تعداد ذکرهای مختلف بازشده: {to_persian_digits(dhikr_unlocked_count)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# بخش ۱۵: تسبیح
# ---------------------------------------------------------------------------


TASBIH_MAX_LEVEL_REACHED = "✨ تسبیح به آخرین سطح رسیده"

TASBIH_UPGRADE_BUTTON_LABEL = "ارتقا 📿"

TASBIH_BACK_BUTTON_LABEL = "↩️ بازگشت به تسبیح"


def tasbih_panel_header(
    tasbih_level: int,
    dhikr_cooldown_seconds: int,
) -> str:
    """کپشن اصلی پنل تسبیح."""
    return tasbih_page(tasbih_level, dhikr_cooldown_seconds)


def tasbih_page(
    tasbih_level: int,
    dhikr_cooldown_seconds: int,
) -> str:
    header = "📿 تسبیح\n"

    level_line = (
        f"سطح فعلی: {to_persian_digits(tasbih_level)} "
        f"از {to_persian_digits(TASBIH_MAX_LEVEL)}"
    )

    cooldown_line = (
        f"⏳ زمان انتظار فعلی ذکر: "
        f"{format_mmss(dhikr_cooldown_seconds)}"
    )

    if tasbih_level >= TASBIH_MAX_LEVEL:
        return (
            f"{header}\n"
            f"{level_line}\n"
            f"{cooldown_line}\n\n"
            f"{TASBIH_MAX_LEVEL_REACHED}"
        )

    cost = get_upgrade_cost(tasbih_level)

    cost_line = f"💫 هزینه ارتقای بعدی: {to_persian_digits(cost)} نور"

    return (
        f"{header}\n"
        f"{level_line}\n"
        f"{cooldown_line}\n"
        f"{cost_line}"
    )


def tasbih_upgrade_confirm(
    next_level: int,
    cost: int,
) -> str:
    return (
        f"می‌خوای تسبیح رو به سطح "
        f"{to_persian_digits(next_level)} ارتقا بدی؟ "
        f"(هزینه: {to_persian_digits(cost)} نور)"
    )


def tasbih_upgrade_success(
    new_level: int,
    new_cooldown_seconds: int,
) -> str:
    return (
        f"✅ تسبیح ارتقا پیدا کرد!\n"
        f"📿 سطح جدید: {to_persian_digits(new_level)}\n"
        f"⏳ زمان انتظار جدید ذکر: "
        f"{format_mmss(new_cooldown_seconds)}"
    )


TASBIH_INSUFFICIENT_NOOR = "💫 نورت برای این ارتقا کافی نیست."


# ---------------------------------------------------------------------------
# بخش ۱۶: صندوقچه
# ---------------------------------------------------------------------------


CHEST_OPEN_BUTTON_LABEL = "باز کردن 🎁"


CHEST_FIRST_TIME_MESSAGE = (
    "🎁 **صندوقچه پیدا کردی!**\n\n"
    "صندوقچه‌ها شانسی پیدا میشن و داخلشون فقط **نور** قرار داره.\n\n"
    "⏳ هر صندوقچه فقط تا **۱ ساعت** قابل باز شدنه.\n\n"
    "🔒 هر نفر هم در هر ۲۴ ساعت فقط می‌تونه یک صندوقچه پیدا کنه."
)


CHEST_SUBSEQUENT_MESSAGE = "🎁 یه صندوقچه‌ی دیگه پیدا کردی!"


CHEST_MOTIVATIONAL_LINES: list[str] = [
    "🌱 **گاهی یک قدم کوچک، شروع یک تغییر بزرگه.**",
    "✨ **هر روز لازم نیست بزرگ شروع کنی؛ فقط کافیه ادامه بدی.**",
    "🌿 **راه‌های بزرگ، از قدم‌های کوچیک ساخته می‌شن.**",
    "💫 **اگر امروز فقط یک قدم جلو رفتی، یعنی هنوز داری پیش می‌ری.**",
    "🌙 **بعضی تغییرها آرام اتفاق می‌افتن؛ درست مثل نوری که کم‌کم بیشتر می‌شه.**",
    "🤲 **خوبی‌های کوچیک، وقتی ادامه پیدا کنن، اثرهای بزرگی می‌سازن.**",
    "🌟 **قرار نیست همیشه سریع پیش بری؛ مهم اینه که از حرکت نایستی.**",
    "🕊️ **گاهی آرام ادامه دادن، خودش یک جور پیروزیه.**",
    "💚 **هر قدمی که با نیت خوب برداشته می‌شه، ارزشمندتر از چیزیه که فکر می‌کنی.**",
    "✨ **شاید همین قدم کوچیک، شروع اتفاق قشنگی باشه که منتظرش نبودی.**",
]


def chest_opened_message(
    reward_noor: int,
    noor_current: int,
    motivational_line: str,
) -> str:
    paragraphs = [
        "🎁✨ **صندوقچه رو باز کردی!**",
        (
            f"🌟 امروز سهم تو از این صندوقچه:\n"
            f"**+{to_persian_digits(reward_noor)} نور**"
        ),
        f"💫 نور معنویتت: **{to_persian_digits(noor_current)}**",
        motivational_line,
        "🤲 قدم بعدیت رو بردار...",
    ]
    return "\n\n".join(paragraphs)


CHEST_NOT_OWNER = "این صندوقچه مال تو نیست."

CHEST_ALREADY_OPENED = "این صندوقچه قبلاً باز شده."

CHEST_EXPIRED = "⌛ این صندوقچه منقضی شده."


# ---------------------------------------------------------------------------
# Level 2 — التماس دعا (نام داخلی: dua_queue)
# ---------------------------------------------------------------------------


def dua_queue_unlocked_message(noor_reward: int, noor_current: int) -> str:
    """
    پیام کامل milestone وقتی سهمیه‌ی ۱۰ ذکر امروز تکمیل می‌شود.
    """
    required = to_persian_digits(dua_queue_domain.DAILY_FREE_DHIKR_REQUIRED)
    lines = [
        "✨ ذکرت ثبت شد",
        f"✨ +{to_persian_digits(noor_reward)} نور",
        f"💫 نور معنویتت: {to_persian_digits(noor_current)}",
        "",
        f"🤲 **امروز {required} ذکر گفتی و یک قابلیت تازه برات باز شد: التماس دعا**",
        (
            "از این‌جا می‌تونی یک پنل «التماس دعا» بسازی و از بقیه‌ی اعضای گروه بخوای برات دعا کنن؛ "
            "هرکس ذکر پنل رو کپی کنه و روی پنل ریپلای بزنه، هم خودش نور می‌گیره، هم تو."
        ),
        "برای ساختن پنل بنویس: **«التماس دعا»**",
        "⏳ این قابلیت فقط برای امروز فعاله؛ فردا سهمیه‌ات دوباره از صفر شروع می‌شه.",
    ]
    return "\n".join(lines)


def dua_queue_panel_text(
    answers_count: int,
    max_answers: int,
    *,
    dhikr_text: str | None = None,
    owner_name: str | None = None,
    owner_telegram_id: int | None = None,
    responders: list[tuple[int, str | None]] | None = None,
    owner_earned: int = 0,
    closed: bool = False,
) -> str:
    """
    متن پنل «التماس دعا» (HTML). ذکر داخل <code> است تا با یک لمس در تلگرام کپی شود.
    اسم دعاکننده‌ها و نور دریافتی صاحب پنل هم روی پنل نمایش داده می‌شود (هم باز، هم بسته).
    """

    def _mention(tg_id: int | None, name: str | None, fallback: str) -> str:
        label = escape(name or fallback)
        if tg_id is None:
            return label
        return f'<a href="tg://user?id={tg_id}">{label}</a>'

    header = "🤲 <b>التماس دعا</b>" if not closed else "🤲 التماس دعا (بسته شد)"
    lines = [header, ""]

    if not closed:
        lines.append(f"{_mention(owner_telegram_id, owner_name, 'یکی از اعضای گروه')} التماس دعا داره.")
        lines.append("")
        lines.append("۱) ذکر زیر رو کپی کن (روی متنش بزن)")
        lines.append("۲) روی همین پیام ریپلای بزن و ذکر رو بفرست")
        lines.append("")
        if dhikr_text is not None:
            lines.append(f"<code>{escape(dhikr_text)}</code>")
            lines.append("")
        lines.append("هم خودت نور می‌گیری، هم به اون کمک می‌کنی. هر نفر فقط یک‌بار می‌تونه جواب بده.")
        lines.append("")
    elif owner_telegram_id is not None or owner_name:
        lines.append(f"صاحب پنل: {_mention(owner_telegram_id, owner_name, 'صاحب پنل')}")
        lines.append("")

    lines.append(f"پاسخ‌ها: {to_persian_digits(answers_count)} از {to_persian_digits(max_answers)}")

    if responders:
        lines.append("")
        lines.append("🤲 دعاکنندگان:")
        for index, (tg_id, name) in enumerate(responders, start=1):
            lines.append(f"{to_persian_digits(index)}. {_mention(tg_id, name, 'کاربر')}")

    lines.append("")
    lines.append(f"✨ نور دریافتی صاحب پنل: {to_persian_digits(owner_earned)}")

    if not closed:
        lines.append("⏳ این پنل حداکثر تا ۱۲ ساعت دیگه بازه.")
    else:
        lines.append("🙏 ممنون از همه‌ی کسایی که پاسخ دادن.")
    return "\n".join(lines)


def dua_queue_answer_success(noor_reward: int, noor_current: int) -> str:
    return (
        "🤲 به التماس دعا پاسخ دادی و ذکرت ثبت شد.\n"
        f"✨ +{to_persian_digits(noor_reward)} نور\n"
        f"💫 نور معنویتت: {to_persian_digits(noor_current)}\n"
        "🙏 صاحب پنل هم به‌خاطر پاسخ تو نور گرفت."
    )


def dua_queue_completed_message(owner_name: str | None, owner_telegram_id: int | None, bonus: int) -> str:
    """پیام گروه وقتی پنل به سقف پاسخ‌ها رسید (HTML)."""
    if owner_telegram_id is not None:
        who = f'<a href="tg://user?id={owner_telegram_id}">{escape(owner_name or "صاحب پنل")}</a>'
    else:
        who = "صاحب پنل"
    return (
        f"🎉 پنل التماس دعای {who} کامل شد و بسته شد.\n"
        f"✨ +{to_persian_digits(bonus)} نور بونوس برای صاحب پنل 🙏"
    )


def dua_queue_quota_not_complete(done: int, required: int) -> str:
    return (
        "🤲 برای ساخت پنل التماس دعا باید امروز "
        f"{to_persian_digits(required)} ذکر (غیر از ذکر حلقه) ثبت کرده باشی.\n"
        f"امروز تا الان: {to_persian_digits(done)} از {to_persian_digits(required)}"
    )


DUA_QUEUE_OWNER_COOLDOWN = "🤲 هر ۲۴ ساعت فقط یک‌بار می‌تونی پنل التماس دعا بسازی. یکم بعد دوباره امتحان کن."

DUA_QUEUE_OWNER_CANNOT_ANSWER = "نمی‌تونی به پنل التماس دعای خودت پاسخ بدی."

DUA_QUEUE_RESPONDER_NOT_STARTED = "برای پاسخ به التماس دعا، اول باید بازی رو با یک صلوات شروع کنی."

DUA_QUEUE_ALREADY_ANSWERED = "قبلاً به این پنل پاسخ دادی."

DUA_QUEUE_CLOSED = "این پنل دیگه بسته شده."

DUA_QUEUE_ANSWER_FAILED = "الان امکان ثبت پاسخ نبود؛ یکم بعد دوباره امتحان کن."

DUA_QUEUE_LEGACY_BUTTON = "این پنل قدیمیه و دیگه با دکمه پاسخ داده نمی‌شه."


# ---------------------------------------------------------------------------
# Level 2 — حلقه ذکر
# ---------------------------------------------------------------------------

CIRCLE_CREATE_BUTTON_LABEL = "➕ ساخت حلقه"
CIRCLE_STATUS_BUTTON_LABEL = "📊 وضعیت حلقه"
CIRCLE_MEMBERS_BUTTON_LABEL = "👥 اعضای حلقه"
CIRCLE_INVITE_BUTTON_LABEL = "🔗 دعوت به حلقه"
CIRCLE_LEAVE_BUTTON_LABEL = "🚪 خروج از حلقه"
CIRCLE_CLAIM_REWARD_BUTTON_LABEL = "🎁 دریافت جایزه"
CIRCLE_MANAGE_BUTTON_LABEL = "⚙️ مدیریت اعضا"
CIRCLE_BACK_BUTTON_LABEL = "🔙 بازگشت"
CIRCLE_INVITE_ACCEPT_BUTTON_LABEL = "✅ قبول دعوت"
CIRCLE_INVITE_CANCEL_BUTTON_LABEL = "❌ رد دعوت"


def circle_intro_text() -> str:
    """اولین باری که کاربر «حلقه ذکر» را می‌فرستد و هنوز عضو هیچ حلقه‌ای نیست."""
    return (
        "🧿 **حلقه ذکر**\n\n"
        "حلقه ذکر یعنی چند نفر کنار هم، هرکس با ریتم خودش، ذکر بگویند.\n\n"
        "🤲 هیچ اجباری در کار نیست: هرکس فقط به‌خاطر فعالیت خودش پاداش می‌گیرد؛ "
        "اگر یکی از اعضا امروز فعالیتی نداشته باشد، هیچ‌کس تنبیه نمی‌شود.\n\n"
        "حلقه با هر تعداد عضو قابل استفاده است؛ عدد ۵ فقط برای یک پاداش ویژه‌ی گروهی "
        "اهمیت دارد (در ادامه توضیح داده می‌شود).\n\n"
        "برای ساختن حلقه‌ی خودت، دکمه‌ی زیر رو بزن."
    )


def circle_main_panel_text(
    circle_name: str,
    display_dhikr,
    members_progress: list[tuple[str, int, int, bool]],
    my_count: int,
    daily_target: int,
    personal_reward_paid: bool,
    group_completed_count: int,
    group_target: int,
    group_reward_paid: bool,
) -> str:
    """
    متن پنل حلقه ذکر.

    members_progress: لیست چهارتایی (label, count, target, is_creator)
    که is_creator یعنی همین عضو، سازنده‌ی حلقه است (برای نمایش 👑).

    نکته‌ی راست‌چین‌سازی: در تلگرام، خطوطی که با @ یا حروف لاتین شروع می‌شوند
    به‌صورت خودکار چپ‌چین می‌شوند. برای یکدست راست‌چین ماندن کل پنل، قبل از هر خط
    کاراکتر نامرئی RLM (U+200F) را می‌گذاریم.
    """
    RLM = "\u200f"  # Right-to-Left Mark

    lines = [
        f"{RLM}🧿 {escape(str(circle_name))}",
        f"{RLM}",
        f"{RLM}📿 ذکر امروز:",
        f"{RLM}<code>{escape(str(display_dhikr.display_name))}</code>",
        f"{RLM}با گفتن این ذکر در گروه، +{to_persian_digits(display_dhikr.noor_reward)} نور می‌گیری.",
        f"{RLM}این ذکر تا ۲۴ ساعت ثابت می‌مونه و بعد یک ذکر جدید انتخاب می‌شه.",
        f"{RLM}",
        f"{RLM}👥 اعضا: {to_persian_digits(len(members_progress))} از {to_persian_digits(group_target)}",
        f"{RLM}",
        f"{RLM}🌿 پیشرفت ذکر امروز:",
    ]

    for label, count, target, is_creator in members_progress:
        filled = min(count, target)
        bar = render_progress_bar(filled, target)
        done = " ✅" if filled >= target else ""
        marker = "👑" if is_creator else "🟢"
        # دو خط برای هر عضو: خط نام، و خط نوار پیشرفت. هر دو با RLM شروع می‌شوند.
        lines.append(f"{RLM}{marker} {escape(str(label))}")
        lines.append(f"{RLM}{bar}{done}")

    if personal_reward_paid:
        personal_reward_line = f"{RLM}🎁 پاداش شخصی امروز: ✅ +۲۵ نور"
    elif my_count >= daily_target:
        personal_reward_line = f"{RLM}🎁 پاداش شخصی امروز: 🎁 آماده‌ی دریافت! دکمه‌ی «دریافت جایزه» رو بزن."
    else:
        personal_reward_line = f"{RLM}🎁 پاداش شخصی امروز: ⏳ با تکمیل ۱۰ ذکر، +۲۵ نور"

    lines.extend([
        f"{RLM}",
        personal_reward_line,
        f"{RLM}",
        f"{RLM}🏆 پاداش گروهی",
        (
            f"{RLM}{to_persian_digits(group_completed_count)} از {to_persian_digits(group_target)} "
            "نفر سهم ۱۰ ذکرشان را کامل کرده‌اند."
        ),
    ])

    if group_reward_paid:
        lines.append(f"{RLM}🎉 پاداش گروهی امروز پرداخت شد: +۱۵ نور برای هر ۵ عضو.")
    else:
        lines.append(f"{RLM}🎁 با تکمیل ۱۰ ذکر توسط هر ۵ عضو، +۱۵ نور برای هر عضو پرداخت می‌شود.")

    lines.extend([
        f"{RLM}",
        f"{RLM}🔗 برای دعوت: روی پیام شخص موردنظر ریپلای کن و بنویس «حلقه ذکر».",
    ])

    return "\n".join(lines)


def circle_already_in_circle() -> str:
    return "تو الان عضو یک حلقه‌ای؛ برای ساخت حلقه‌ی جدید، اول باید از حلقه‌ی فعلی خارج بشی."


def circle_status_text(
    daily_count: int,
    daily_target: int,
    members_progress: list[tuple[str, int, int]],
    completed_count: int,
    milestone_min_members: int,
    milestone_total_noor: int,
    milestone_reward_each: int,
    milestone_paid_today: bool,
) -> str:
    lines = [
        "📊 **وضعیت حلقه**",
        "",
        f"🤲 سهم امروز تو:\n{to_persian_digits(daily_count)} از {to_persian_digits(daily_target)}",
        "",
        "👥 اعضای حلقه:",
    ]
    for label, count, target in members_progress:
        lines.append(f"{label} — {to_persian_digits(count)}/{to_persian_digits(target)}")

    lines.append("")
    lines.append("⭐ پیشرفت پاداش گروهی:")
    lines.append(
        f"{to_persian_digits(completed_count)} از {to_persian_digits(milestone_min_members)} عضو "
        "امروز سهمشون رو کامل کرده‌اند."
    )
    if milestone_paid_today:
        lines.append("🎁 پاداش گروهی امروز قبلاً بین ۵ نفر اول تقسیم شد.")
    else:
        lines.append(
            f"🎁 اگر {to_persian_digits(milestone_min_members)} نفر همین امروز سهمشون رو کامل کنند، "
            f"{to_persian_digits(milestone_total_noor)} نور بینشون تقسیم می‌شه "
            f"(هرکدام {to_persian_digits(milestone_reward_each)} نور)."
        )
    return "\n".join(lines)


def circle_members_text(members: list[tuple[str, bool]]) -> str:
    """members: لیست (نمایش‌نام, آیا_سازنده_است) به ترتیب پیوستن."""
    lines = ["👥 **اعضای حلقه**", ""]
    for label, is_creator in members:
        marker = "👑" if is_creator else "🟢"
        lines.append(f"{marker} {label}")
    return "\n".join(lines)


def circle_invite_text(invite_link: str) -> str:
    return (
        "🔗 **دعوت به حلقه**\n\n"
        f"{invite_link}"
    )


def circle_invite_instruction() -> str:
    return "برای دعوت یک نفر، روی پیام همان کاربر ریپلای کن و فقط بنویس: «حلقه ذکر»"


def circle_invite_confirmation(target_label: str, inviter_label: str) -> str:
    return (
        "🧿 **دعوت به حلقه ذکر**\n\n"
        f"{inviter_label} ازت دعوت کرده به حلقه ذکرش بپیوندی.\n\n"
        "اگر قبول کنی، همین حالا وارد حلقه می‌شی."
    )


def circle_invite_sent(target_label: str) -> str:
    return f"📨 دعوت حلقه برای {target_label} ارسال شد."


CIRCLE_INVITE_REQUIRES_LEVEL_2 = "برای دعوت به حلقه، اول باید وارد سطح ۲ شده باشی."
CIRCLE_INVITE_TARGET_ALREADY_IN_CIRCLE = "این کاربر همین حالا عضو یک حلقه است."
CIRCLE_INVITE_TARGET_NOT_LEVEL_2 = "این کاربر هنوز به سطح ۲ نرسیده است."
CIRCLE_INVITE_TARGET_MUST_START_BOT = "نتونستم پیام خصوصی دعوت رو برای این کاربر بفرستم؛ باید یک‌بار ربات رو Start کرده باشه."
CIRCLE_INVITE_FULL = "ظرفیت حلقه تکمیل شده است."
CIRCLE_INVITE_EXPIRED = "این دعوت دیگر معتبر نیست."
CIRCLE_INVITE_DECLINED = "دعوت به حلقه رد شد."


def circle_invite_accepted() -> str:
    return "✅ دعوت را قبول کردی و وارد حلقه شدی."


def circle_leave_ask() -> str:
    return "🚪 مطمئنی می‌خوای از حلقه خارج بشی؟"


def circle_leave_locked(hours_left: int) -> str:
    return (
        "🚪 هنوز نمی‌تونی از حلقه خارج بشی.\n"
        f"تا حدود {to_persian_digits(hours_left)} ساعت دیگه صبر کن (محدودیت ۷۲ ساعته‌ی عضویت)."
    )


CIRCLE_LEFT_SUCCESS = "🚪 از حلقه خارج شدی. هر وقت خواستی می‌تونی دوباره یک حلقه بسازی یا عضو یکی دیگه بشی."

CIRCLE_NOT_IN_CIRCLE = "تو الان عضو هیچ حلقه‌ای نیستی."

CIRCLE_JOIN_ALREADY_IN_CIRCLE = "تو الان عضو یک حلقه‌ی دیگه‌ای؛ برای پیوستن به این حلقه، اول باید از حلقه‌ی فعلی خارج بشی."

CIRCLE_JOIN_NOT_FOUND = "این حلقه دیگه وجود نداره."


def circle_join_success() -> str:
    return (
        "🧿 با موفقیت به حلقه پیوستی!\n"
        "سهم روزانه‌ات از همین الان از صفر شروع شد.\n"
        "برای دیدن وضعیت حلقه، بنویس: «حلقه ذکر»"
    )


def circle_manage_text() -> str:
    return "⚙️ **مدیریت اعضا**\n\nروی نام هرکس بزنی، امکان حذفش رو می‌بینی."


CIRCLE_MANAGE_NO_MEMBERS = "⚙️ به‌جز خودت، عضو دیگری در حلقه نیست."

CIRCLE_MANAGE_NOT_CREATOR = "فقط سازنده‌ی حلقه می‌تونه عضو حذف کنه."


def circle_remove_ask(label: str) -> str:
    return f"❌ مطمئنی می‌خوای {label} رو از حلقه حذف کنی؟"


def circle_remove_locked(label: str, hours_left: int) -> str:
    return (
        f"❌ {label} هنوز در بازه‌ی ۷۲ ساعته‌ی عضویتشه و نمی‌تونی حذفش کنی.\n"
        f"تا حدود {to_persian_digits(hours_left)} ساعت دیگه صبر کن."
    )


def circle_remove_success(label: str) -> str:
    return f"❌ {label} از حلقه حذف شد."


CIRCLE_DAILY_TARGET_COMPLETE = "🎉 سهم امروزت در حلقه کامل شد!"


CIRCLE_REWARD_NOT_READY = "هنوز سهم امروزت (۱۰ ذکر) در حلقه کامل نشده که جایزه بگیری."
CIRCLE_REWARD_ALREADY_CLAIMED = "جایزه‌ی امروزت رو قبلاً دریافت کردی."


def circle_reward_group_announcement(mention: str, reward_noor: int) -> str:
    return (
        f"🎁 {mention} سهم امروزش رو در حلقه ذکر کامل کرد و "
        f"{to_persian_digits(reward_noor)} نور جایزه گرفت! 🎉"
    )


def circle_milestone_announcement(winner_labels: list[str], reward_each: int, total: int) -> str:
    names = "، ".join(winner_labels)
    return (
        "🎉 **پاداش گروهی حلقه فعال شد!**\n"
        f"{to_persian_digits(len(winner_labels))} عضو امروز سهمشون رو کامل کردند: {names}\n"
        f"🎁 هرکدام {to_persian_digits(reward_each)} نور گرفتند (مجموعاً {to_persian_digits(total)} نور)."
    )
