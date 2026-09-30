"""
ذکر اصلی بازی: «اللهم عجل لولیک الفرج».

توجه: نام‌های SALAWAT_* و ActivityKind.SALAWAT عمداً تغییر نکرده‌اند تا بقیه‌ی پروژه دست‌نخورده
بماند؛ ولی از این به بعد «فعالیت اصلی بازی» همین ذکر است و صلوات قبلی دیگر معتبر نیست.

برای اضافه کردن نسخه‌ی جدید در آینده، کافیست یک رشته‌ی جدید به _BASE_VARIANTS اضافه شود.
املاهای رایج (ک/ك، ی/ي، اعراب، تشدید) خودشان توسط normalize_text یکی می‌شوند.
"""
from __future__ import annotations

from bot.domain.normalization import normalize_text

_BASE_VARIANTS: list[str] = [
    "اللهم عجل لولیک الفرج",
    "اللهم عجل لوليك الفرج",
    "اَللّهُمَّ عَجِّلْ لِوَلِیِّکَ الْفَرَجَ",
    "الله‌م عجل لولیک الفرج",
]

SALAWAT_VARIANTS: list[str] = list(_BASE_VARIANTS)

# مقدار نور و پیشرفتی که هر صلوات معتبر می‌دهد (بخش ۳)
SALAWAT_NOOR_REWARD = 8
SALAWAT_PROGRESS_STEP = 1

# سطح ۱ = ۵ ذکر. بعد از ۵/۵ باید درس ۱ «مسیر انتظار» قبول شود؛ ذکر بعدی کاربر را به سطح ۲ می‌برد
# و پیشرفت سطح ۲ از 1/24 نمایش داده می‌شود.
LEVEL_1_REQUIRED_SALAWAT = 5
LEVEL_2_REQUIRED_SALAWAT = 24
# Level 3 starts with the salawat that follows 24/24 of level 2; it is displayed as 1/N.
# [PLACEHOLDER] تعداد صلوات لازم برای سطح ۳ در سند مشخص نشده.
LEVEL_3_REQUIRED_SALAWAT = 36


def get_level_required_salawat(level: int) -> int:
    """تعداد صلوات لازم برای کامل شدن پیشرفت هر سطح (برای نوار پیشرفت)."""
    if level >= 3:
        return LEVEL_3_REQUIRED_SALAWAT
    if level == 2:
        return LEVEL_2_REQUIRED_SALAWAT
    return LEVEL_1_REQUIRED_SALAWAT

# مجموعه‌ی نرمال‌شده برای jlookup سریع و بدون ابهام
_NORMALIZED_SET: set[str] = {normalize_text(v) for v in SALAWAT_VARIANTS}


def is_valid_salawat(normalized_text: str) -> bool:
    """آیا متن نرمال‌شده دقیقاً برابر یکی از نسخه‌های معتبر صلوات است؟"""
    return normalized_text in _NORMALIZED_SET


def looks_like_salawat_attempt(normalized_text: str) -> bool:
    """
    فیلتر سبک برای تشخیص «شاید این یک تلاش برای ذکر اصلی باشد» — نه validation دقیق.
    فقط برای این استفاده می‌شود که پیام‌های کاملاً بی‌ربط چت گروه را نادیده بگیریم
    و روی آن‌ها پیام «نامعتبر» نفرستیم. اعتبارسنجی واقعی همچنان دقیق و بدون fuzzy matching
    توسط is_valid_salawat انجام می‌شود.
    """
    return ("عجل" in normalized_text) or ("فرج" in normalized_text)
