"""
مکانیزم اصلی ضدّ پردازش دوباره (بخش ۲۰ سند: retry تلگرام، double click، ارسال همزمان).

هر update تلگرام (پیام یا callback) دقیقاً یک‌بار «claim» می‌شود: تلاش برای insert کردن
update_id در جدول processed_updates. اگر insert به‌خاطر UNIQUE constraint شکست بخورد،
یعنی این update قبلاً پردازش شده و باید بی‌سروصدا نادیده گرفته شود.

این claim در همان تراکنشی انجام می‌شود که بقیه‌ی تغییرات دیتابیس (نور، Progress، unlock و ...)
هم در آن اتفاق می‌افتند، پس اگر منطق کسب‌وکار fail کند، claim هم rollback می‌شود و امکان
retry موفق در آینده باقی می‌ماند.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def try_claim_update(session: AsyncSession, update_id: int) -> bool:
    """
    تلاش می‌کند update_id را claim کند. True یعنی برای اولین‌بار است (ادامه بده).
    False یعنی قبلاً پردازش شده (باید بی‌صدا متوقف شوی).
    """
    try:
        await session.execute(
            text("INSERT INTO processed_updates(update_id, processed_at) VALUES (:uid, :ts)"),
            {"uid": update_id, "ts": datetime.now(timezone.utc).isoformat()},
        )
        # flush زودهنگام تا خطای UNIQUE همین‌جا گرفته شود، نه در commit نهایی
        await session.flush()
        return True
    except IntegrityError:
        await session.rollback()
        return False
