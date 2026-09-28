"""
تعریف ذکرها (بخش ۵ و ۶ سند).

برای اضافه کردن ذکر جدید در آینده، کافیست یک DhikrDefinition جدید به DHIKR_LIST
اضافه شود (با key منحصربه‌فرد). بقیه‌ی سیستم (بانک اذکار، unlock، ثبت فعالیت)
به‌صورت خودکار آن را پشتیبانی می‌کند.

توجه: طبق بخش ۲۴ (TODO)، threshold سطح باز شدن ذکرهای آینده هنوز مشخص نشده و
نباید توسط ما اختراع شود؛ فعلاً هر ۴ ذکر از همان ابتدای Level 1 (بعد از unlock) قابل استفاده‌اند.
"""
from __future__ import annotations

from dataclasses import dataclass

from bot.domain.normalization import normalize_text


@dataclass(frozen=True)
class DhikrDefinition:
    key: str  # شناسه داخلی پایدار (در دیتابیس و callback data استفاده می‌شود)
    display_name: str  # نام نمایشی
    canonical_texts: tuple[str, ...]  # متن(های) معتبر برای این ذکر
    noor_reward: int  # نور هر بار استفاده
    unlock_cost: int  # هزینه‌ی unlock (۰ یعنی رایگان/از ابتدا باز)
    # کولداون اختصاصی این ذکر (ثانیه). None یعنی کولداون معمول بر اساس سطح تسبیح.
    cooldown_seconds: int | None = None


DHIKR_LIST: list[DhikrDefinition] = [
    DhikrDefinition(
        key="alhamdulillah",
        display_name="الحمدلله",
        canonical_texts=("الحمدلله",),
        noor_reward=5,
        unlock_cost=0,
        cooldown_seconds=1,
    ),
    DhikrDefinition(
        key="la_ilaha_illallah",
        display_name="لا اله الا الله",
        canonical_texts=("لا اله الا الله",),
        noor_reward=6,
        unlock_cost=300,
    ),
    DhikrDefinition(
        key="subhanallah",
        display_name="سبحان الله",
        canonical_texts=("سبحان الله",),
        noor_reward=7,
        unlock_cost=700,
    ),
    DhikrDefinition(
        key="allahu_akbar",
        display_name="الله اکبر",
        canonical_texts=("الله اکبر",),
        noor_reward=8,
        unlock_cost=1500,
    ),
    # ---------------------------------------------------------------------
    # ذکرهای ویژه‌ی «حلقه ذکر»: هر بار که کاربر می‌نویسد «حلقه ذکر»، یکی از
    # این ۵ ذکر به‌صورت تصادفی برایش انتخاب و تا ۲۴ ساعت ثابت نگه داشته
    # می‌شود (bot/services/dhikr_circle_service.py). رایگان و از ابتدا بازند
    # (unlock_cost=0) تا همان لحظه که نمایش داده می‌شوند قابل‌استفاده باشند.
    # ---------------------------------------------------------------------
    DhikrDefinition(
        key="istighfar_long",
        display_name="استغفر الله ربی و اتوب الیه",
        canonical_texts=("استغفر الله ربی و اتوب الیه",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="la_hawla",
        display_name="لا حول و لا قوة الا بالله",
        canonical_texts=("لا حول و لا قوة الا بالله",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="subhanallah_wa_bihamdihi",
        display_name="سبحان الله و بحمده",
        canonical_texts=("سبحان الله و بحمده",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="hasbunallah",
        display_name="حسبنا الله و نعم الوکیل",
        canonical_texts=("حسبنا الله و نعم الوکیل",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="ya_allah_rahman_rahim",
        display_name="یا الله یا رحمن یا رحیم",
        canonical_texts=("یا الله یا رحمن یا رحیم",),
        noor_reward=10,
        unlock_cost=0,
    ),
]

# کلیدهای همان ۵ ذکر ویژه‌ی بالا، برای انتخاب تصادفی در جریان «حلقه ذکر».
CIRCLE_DISPLAY_DHIKR_KEYS: tuple[str, ...] = (
    "istighfar_long",
    "la_hawla",
    "subhanallah_wa_bihamdihi",
    "hasbunallah",
    "ya_allah_rahman_rahim",
)

# ---------------------------------------------------------------------------
# ذکرهای «التماس دعا» (Level 2): یکی از این ۵ ذکر هنگام ساخت هر پنل به‌صورت تصادفی
# انتخاب می‌شود. عمداً داخل DHIKR_LIST نیستند تا بیرون از پنل (در چت عادی) نور ندهند؛
# فقط از مسیر ریپلای روی پنل (dua_queue_service) ثبت می‌شوند. رایگان و بدون قفل‌اند.
# ---------------------------------------------------------------------------
DUA_QUEUE_DHIKR_LIST: list[DhikrDefinition] = [
    DhikrDefinition(
        key="dua_ighfir_lahu_warhamhu",
        display_name="اللهم اغفر له وارحمه",
        canonical_texts=("اللهم اغفر له وارحمه",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="dua_afu_anhu_wa_afihi",
        display_name="اللهم اعف عنه وعافه",
        canonical_texts=("اللهم اعف عنه وعافه",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="dua_irhamhu_waghfir_lahu",
        display_name="اللهم ارحمه واغفر له",
        canonical_texts=("اللهم ارحمه واغفر له",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="dua_ighfir_laha_warhamha",
        display_name="اللهم اغفر لها وارحمها",
        canonical_texts=("اللهم اغفر لها وارحمها",),
        noor_reward=10,
        unlock_cost=0,
    ),
    DhikrDefinition(
        key="dua_afu_anha_wa_afiha",
        display_name="اللهم اعف عنها وعافها",
        canonical_texts=("اللهم اعف عنها وعافها",),
        noor_reward=10,
        unlock_cost=0,
    ),
]

DUA_QUEUE_DHIKR_BY_KEY: dict[str, DhikrDefinition] = {d.key: d for d in DUA_QUEUE_DHIKR_LIST}

# متن‌های نرمال‌شده‌ی همین ۵ ذکر — برای فیلتر سریع پیام‌های ریپلای (بدون کوئری دیتابیس).
DUA_QUEUE_NORMALIZED_TEXTS: frozenset[str] = frozenset(
    normalize_text(t) for d in DUA_QUEUE_DHIKR_LIST for t in d.canonical_texts
)

DHIKR_BY_KEY: dict[str, DhikrDefinition] = {d.key: d for d in DHIKR_LIST}

# نگاشت متن نرمال‌شده -> کلید ذکر، برای lookup سریع و دقیق (بدون fuzzy matching)
_NORMALIZED_TO_KEY: dict[str, str] = {}
for _d in DHIKR_LIST:
    for _text in _d.canonical_texts:
        _NORMALIZED_TO_KEY[normalize_text(_text)] = _d.key


def match_dhikr_key(normalized_text: str) -> str | None:
    """اگر متن نرمال‌شده دقیقاً یکی از ذکرهای معتبر باشد، کلید آن را برمی‌گرداند."""
    return _NORMALIZED_TO_KEY.get(normalized_text)


def looks_like_dhikr_attempt(normalized_text: str) -> bool:
    """
    فیلتر سبک engagement (نه validation) — تشخیص اینکه پیام شاید تلاشی برای یک ذکر بوده،
    تا پیام‌های کاملاً بی‌ربط چت گروه نادیده گرفته شوند.
    """
    roots = ("حمد", "اله", "سبحان", "اکبر", "اكبر", "غفر", "حول", "وکیل", "وكيل", "رحمن", "رحیم", "رحيم")
    return any(root in normalized_text for root in roots)
