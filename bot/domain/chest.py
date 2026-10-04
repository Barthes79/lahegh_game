"""
منطق صندوقچه (اصلاحات نهایی تأییدشده).

دو تایمر مستقل و کاملاً جدا از هم:
- CHEST_FIND_COOLDOWN (۲۴ ساعت): فاصله‌ی لازم بین *پیدا شدن* دو صندوقچه، از لحظه‌ی
  پیدا شدن صندوقچه‌ی قبلی حساب می‌شود (چه باز شود چه نشود).
- CHEST_OPEN_WINDOW (۱ ساعت): مهلتی که کاربر برای *باز کردن* یک صندوقچه‌ی پیداشده دارد.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

CHEST_CHANCE = 0.02  # ۲٪ ثابت (نه بازه‌ای)

CHEST_MIN_REWARD = 40
CHEST_MAX_REWARD = 72

CHEST_OPEN_WINDOW = timedelta(hours=1)  # مهلت باز کردن صندوقچه‌ی پیداشده
CHEST_FIND_COOLDOWN = timedelta(hours=24)  # فاصله‌ی لازم بین پیدا شدن دو صندوقچه


def roll_chest_found() -> bool:
    """بعد از هر فعالیت معتبرِ واقعاً ثبت‌شده صدا زده می‌شود: شانس ثابت ۲٪."""
    return random.random() < CHEST_CHANCE


def roll_chest_reward() -> int:
    return random.randint(CHEST_MIN_REWARD, CHEST_MAX_REWARD)


def can_create_new_chest(last_chest_created_at: datetime | None, now: datetime | None = None) -> bool:
    """
    تا ۲۴ ساعت از زمان پیدا شدن صندوقچه‌ی قبلی نگذشته باشد، صندوق دوم ایجاد نشود
    (مستقل از اینکه صندوقچه‌ی قبلی باز شده باشد یا نه).
    """
    if last_chest_created_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    if last_chest_created_at.tzinfo is None:
        last_chest_created_at = last_chest_created_at.replace(tzinfo=timezone.utc)
    return now - last_chest_created_at >= CHEST_FIND_COOLDOWN


def compute_expiry(created_at: datetime) -> datetime:
    """مهلت باز کردن صندوقچه: ۱ ساعت از لحظه‌ی پیدا شدن."""
    return created_at + CHEST_OPEN_WINDOW


def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now >= expires_at
