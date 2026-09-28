"""
اعتبارسنجی و دسته‌بندی فعالیت (بخش ۴، ۵ و ۸ سند).

نکته‌ی مهم درباره‌ی پیام‌های کاملاً بی‌ربط گروه:
سند مشخص نکرده که آیا ربات باید به هر پیام بی‌ربط در گروه هم پاسخ «نامعتبر» بدهد یا نه.
برای جلوگیری از اسپم روی چت عادی گروه، اینجا یک فیلتر سبک engagement اضافه شده:
فقط پیام‌هایی که واقعاً شبیه یک تلاش برای صلوات/ذکر هستند وارد مسیر validation می‌شوند؛
در غیر این صورت پیام به‌عنوان «چت عادی» نادیده گرفته می‌شود (نه نامعتبر).
این یک فرض طراحی است که باید توسط کارفرما تأیید شود (به گزارش پایانی مراجعه کن).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from bot.domain.dhikr_data import looks_like_dhikr_attempt, match_dhikr_key
from bot.domain.normalization import normalize_text
from bot.domain.salawat_data import is_valid_salawat, looks_like_salawat_attempt


class ActivityKind(Enum):
    SALAWAT = auto()
    DHIKR = auto()
    INVALID_ATTEMPT = auto()  # شبیه تلاش بود ولی نامعتبر (بخش ۸)
    UNRELATED = auto()  # چت عادی/بی‌ربط -> کاملاً نادیده گرفته شود


@dataclass(frozen=True)
class ClassificationResult:
    kind: ActivityKind
    dhikr_key: str | None = None  # فقط وقتی kind == DHIKR
    resembles: "ActivityKind | None" = None  # فقط وقتی kind == INVALID_ATTEMPT


def classify_message(raw_text: str) -> ClassificationResult:
    normalized = normalize_text(raw_text)

    if not normalized:
        return ClassificationResult(ActivityKind.UNRELATED)

    if is_valid_salawat(normalized):
        return ClassificationResult(ActivityKind.SALAWAT)

    dhikr_key = match_dhikr_key(normalized)
    if dhikr_key is not None:
        return ClassificationResult(ActivityKind.DHIKR, dhikr_key=dhikr_key)

    looks_salawat = looks_like_salawat_attempt(normalized)
    looks_dhikr = looks_like_dhikr_attempt(normalized)
    if looks_salawat or looks_dhikr:
        resembles = ActivityKind.SALAWAT if looks_salawat else ActivityKind.DHIKR
        return ClassificationResult(ActivityKind.INVALID_ATTEMPT, resembles=resembles)

    return ClassificationResult(ActivityKind.UNRELATED)
