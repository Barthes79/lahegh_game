"""
عملیات پایه‌ی مربوط به کاربر: پیدا کردن یا ساختن رکورد کاربر.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: str | None, first_name: str | None
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is not None:
        # به‌روزرسانی سبک اطلاعات نمایشی (بدون اثر روی منطق بازی)
        changed = False
        if username != user.username:
            user.username = username
            changed = True
        if first_name != user.first_name:
            user.first_name = first_name
            changed = True
        if changed:
            await session.flush()
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()
    return user
