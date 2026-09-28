"""
لیست نسخه‌های معتبر صلوات (بخش ۴ سند).

برای اضافه کردن نسخه‌ی جدید در آینده، کافیست یک رشته‌ی جدید به SALAWAT_VARIANTS
اضافه شود. هیچ تغییر دیگری در منطق برنامه لازم نیست.
"""
from __future__ import annotations

from bot.domain.normalization import normalize_text

# نسخه‌های خام (قبل از normalize) — طبق اصلاحات نهایی (بند ۱: افزایش از ۶ به ~۱۵-۲۰ نسخه).
#
# به‌جای لیست کردن دستی و مستعد خطا، نسخه‌ها از ترکیب سیستماتیک دو بُعد ساخته می‌شوند:
#   ۱) شکل «آل/ال» + فاصله‌ی «و» قبل از آن (جدا/چسبیده) در جمله‌ی پایه
#   ۲) پسوند «و عجل فرجهم» به چهار شکل رایج (بدون پسوند، جدا/چسبیده، با/بدون «الله»)
# نتیجه ۴ × ۵ = ۲۰ نسخه‌ی معتبر می‌شود. توجه: چون normalize_text خودش «علی/على» را یکی
# می‌کند، لازم نیست این دو را جدا اینجا تکرار کنیم.
_BASE_VARIANTS: list[str] = [
    "اللهم صل علی محمد و آل محمد",
    "اللهم صل علی محمد وآل محمد",
    "اللهم صل علی محمد و ال محمد",
    "اللهم صل علی محمد وال محمد",
]

_FARAJ_SUFFIXES: list[str] = [
    "",
    " و عجل فرجهم",
    " وعجل فرجهم",
    " و عجل الله فرجهم",
    " وعجل الله فرجهم",
]

SALAWAT_VARIANTS: list[str] = [
    f"{base}{suffix}" for base in _BASE_VARIANTS for suffix in _FARAJ_SUFFIXES
]

# مقدار نور و پیشرفتی که هر صلوات معتبر می‌دهد (بخش ۳)
SALAWAT_NOOR_REWARD = 8
SALAWAT_PROGRESS_STEP = 1

# مجموع صلوات لازم برای Level 1 -> Level 2 (بخش ۳)
LEVEL_1_REQUIRED_SALAWAT = 12
# Level 2 starts with the 13th salawat; its progress is displayed as 1/24.
LEVEL_2_REQUIRED_SALAWAT = 24

# مجموعه‌ی نرمال‌شده برای jlookup سریع و بدون ابهام
_NORMALIZED_SET: set[str] = {normalize_text(v) for v in SALAWAT_VARIANTS}


def is_valid_salawat(normalized_text: str) -> bool:
    """آیا متن نرمال‌شده دقیقاً برابر یکی از نسخه‌های معتبر صلوات است؟"""
    return normalized_text in _NORMALIZED_SET


def looks_like_salawat_attempt(normalized_text: str) -> bool:
    """
    فیلتر سبک برای تشخیص «شاید این یک تلاش برای صلوات باشد» — نه validation دقیق.
    فقط برای این استفاده می‌شود که پیام‌های کاملاً بی‌ربط چت گروه را نادیده بگیریم
    و روی آن‌ها پیام «نامعتبر» نفرستیم. اعتبارسنجی واقعی همچنان دقیق و بدون fuzzy matching
    توسط is_valid_salawat انجام می‌شود.
    """
    return ("صل" in normalized_text) and ("محمد" in normalized_text)
