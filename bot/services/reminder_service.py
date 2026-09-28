"""
یادآوری غیرفعالی ۱۲ ساعته (بخش ۱۷ سند).

فاصله‌ی حداقل بین دو یادآوری متوالی، طبق قانون سند ("این را در سیستم قابل‌تنظیم قرار بده")
از bot.config.settings.reminder_min_gap_hours خوانده می‌شود؛ نه هاردکد.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import User


def build_user_mention(user: User) -> str:
    """منشن HTML کاربر (بدون نیاز به username)."""
    name = user.first_name or user.username or "کاربر"
    return f'<a href="tg://user?id={user.telegram_id}">{name}</a>'


async def get_users_due_for_reminder(session: AsyncSession, now: datetime | None = None) -> list[User]:
    now = now or datetime.now(timezone.utc)
    inactivity_cutoff = now - timedelta(hours=settings.reminder_inactivity_hours)
    reminder_gap_cutoff = now - timedelta(hours=settings.reminder_min_gap_hours)

    result = await session.execute(
        select(User).where(
            User.game_started.is_(True),
            User.active_chat_id.is_not(None),
            User.last_activity_at.is_not(None),
            User.last_activity_at <= inactivity_cutoff,
        )
    )
    candidates = list(result.scalars().all())

    due: list[User] = []
    for user in candidates:
        if user.last_reminder_at is None or user.last_reminder_at <= reminder_gap_cutoff:
            due.append(user)
    return due


def mark_reminded(user: User, now: datetime | None = None) -> None:
    user.last_reminder_at = now or datetime.now(timezone.utc)
