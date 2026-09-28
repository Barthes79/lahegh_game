"""
Normalization برای متن‌های عربی/فارسی طبق بخش ۴ سند مشخصات.

قوانین:
- فاصله‌های اضافی و چندگانه یکی می‌شوند.
- نیم‌فاصله (ZWNJ) نادیده گرفته می‌شود (به‌عنوان فاصله در نظر گرفته و بعد collapse می‌شود).
- تفاوت «ی/ي/ى» و «ک/ك» نادیده گرفته می‌شود.
- اعراب (فتحه، ضمه، کسره، تنوین، سکون، شدّه و ...) حذف می‌شوند.
- کشیده «ـ» (tatweel) حذف می‌شود.

توجه: این normalization عمداً تفاوت «آل» و «ال» یا «علی» و «على» را از بین نمی‌برد،
چون هرکدام نسخه‌ی جداگانه‌ای در لیست صلوات‌های معتبر هستند و باید جدا مدیریت شوند.
"""
from __future__ import annotations

import re
import unicodedata

# محدوده یونیکد اعراب و علائم قرآنی که باید حذف شوند
_DIACRITICS_PATTERN = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u08D3-\u08E1\u08E3-\u08FF]"
)

_TATWEEL = "\u0640"  # ـ
_ZWNJ = "\u200C"  # نیم‌فاصله
_ZWSP = "\u200B"  # zero-width space (احتیاطی)

_CHAR_MAP = {
    "\u064A": "\u06CC",  # ي (عربی) -> ی (فارسی)
    "\u0649": "\u06CC",  # ى (الف مقصوره) -> ی
    "\u06CC": "\u06CC",  # ی فارسی، بدون تغییر
    "\u0643": "\u06A9",  # ك (عربی) -> ک (فارسی)
    "\u06A9": "\u06A9",  # ک فارسی، بدون تغییر
}


def normalize_text(text: str) -> str:
    """متن ورودی را طبق قوانین بخش ۴ نرمال‌سازی می‌کند."""
    if text is None:
        return ""

    # یکسان‌سازی یونیکد (NFC) برای جلوگیری از مشکلات ترکیب کاراکتر
    text = unicodedata.normalize("NFC", text)

    # حذف اعراب و علائم قرآنی
    text = _DIACRITICS_PATTERN.sub("", text)

    # حذف کشیده
    text = text.replace(_TATWEEL, "")

    # نیم‌فاصله و zero-width space به فاصله معمولی تبدیل شوند (بعداً collapse می‌شوند)
    text = text.replace(_ZWNJ, " ").replace(_ZWSP, " ")

    # یکسان‌سازی حروف ی/ي/ى و ک/ك
    text = "".join(_CHAR_MAP.get(ch, ch) for ch in text)

    # collapse چند فاصله به یک فاصله + حذف فاصله‌های ابتدا/انتها
    text = re.sub(r"\s+", " ", text).strip()

    return text
