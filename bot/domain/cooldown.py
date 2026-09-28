"""
منطق cooldown صلوات و ذکر (بخش ۷ سند). این دو کاملاً مستقل از هم هستند.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SALAWAT_FIRST_COOLDOWN_SECONDS = 1  # اولین صلوات: ۰:۱۰
SALAWAT_COOLDOWN_SECONDS = 1  # صلوات‌های بعدی: ۰:۱۰


def get_salawat_cooldown_seconds(salawat_count_before: int) -> int:
    """cooldown صلوات بعدی، بر اساس تعداد صلوات معتبر قبلی کاربر."""
    if salawat_count_before <= 0:
        return SALAWAT_FIRST_COOLDOWN_SECONDS
    return SALAWAT_COOLDOWN_SECONDS


def remaining_seconds(last_at: datetime | None, cooldown_seconds: int, now: datetime | None = None) -> int:
    """
    ثانیه‌های باقی‌مانده تا پایان cooldown. اگر cooldown تمام شده یا فعالیتی ثبت نشده، ۰.
    """
    if last_at is None:
        return 0
    now = now or datetime.now(timezone.utc)
    if last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    ready_at = last_at + timedelta(seconds=cooldown_seconds)
    remaining = (ready_at - now).total_seconds()
    return max(0, int(remaining + 0.999))  # round up تا کاربر عدد ۰:۰۰ زودتر از موعد نبیند


def is_on_cooldown(last_at: datetime | None, cooldown_seconds: int, now: datetime | None = None) -> bool:
    return remaining_seconds(last_at, cooldown_seconds, now) > 0
