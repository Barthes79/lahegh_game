"""
منطق unlock کردن ذکر (بخش ۶ سند).

atomicity: قید UNIQUE(user_id, dhikr_key) روی جدول dhikr_unlocks تضمین می‌کند که حتی اگر
دو درخواست unlock هم‌زمان (مثلاً double click) به این تابع برسند، فقط یکی موفق به insert
می‌شود و دیگری با خطای IntegrityError مواجه می‌شود (که به‌عنوان "قبلاً باز شده" مدیریت می‌شود).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DhikrUnlock, User
from bot.domain.dhikr_data import DhikrDefinition


class UnlockResult:
    SUCCESS = "success"
    ALREADY_UNLOCKED = "already_unlocked"
    INSUFFICIENT_NOOR = "insufficient_noor"


@dataclass
class UnlockOutcome:
    result: str
    noor_current: int = 0


async def is_unlocked(session: AsyncSession, user: User, dhikr: DhikrDefinition) -> bool:
    if dhikr.unlock_cost == 0:
        return True
    result = await session.execute(
        select(DhikrUnlock).where(DhikrUnlock.user_id == user.id, DhikrUnlock.dhikr_key == dhikr.key)
    )
    return result.scalar_one_or_none() is not None


async def unlock_dhikr(session: AsyncSession, user: User, dhikr: DhikrDefinition) -> UnlockOutcome:
    if await is_unlocked(session, user, dhikr):
        return UnlockOutcome(result=UnlockResult.ALREADY_UNLOCKED, noor_current=user.noor_current)

    if user.noor_current < dhikr.unlock_cost:
        return UnlockOutcome(result=UnlockResult.INSUFFICIENT_NOOR, noor_current=user.noor_current)

    user.noor_current -= dhikr.unlock_cost
    # توجه: noor_total_earned کاهش پیدا نمی‌کند (بخش ۱۸: total earned فقط با کسب نور زیاد می‌شود)

    try:
        session.add(
            DhikrUnlock(user_id=user.id, dhikr_key=dhikr.key, unlocked_at=datetime.now(timezone.utc))
        )
        await session.flush()
    except IntegrityError:
        # یک درخواست هم‌زمان دیگر زودتر موفق شده -> نور را برنگردان (چون آن یکی هم کسر کرده)
        # در واقع rollback کل تراکنش لازم است تا وضعیت سازگار بماند؛ caller این را مدیریت می‌کند.
        raise

    return UnlockOutcome(result=UnlockResult.SUCCESS, noor_current=user.noor_current)
