"""
سرویس «نماز اول وقت»: گرفتن اوقات شرعی از Aladhan API (با کش روزانه) و ثبت «نماز اول وقت خواندم».

- اوقات هر روز فقط یک بار گرفته و در حافظه کش می‌شود. اگر API خطا بدهد، ۶۰ ثانیه دوباره تلاش
  نمی‌شود و تا آن موقع همه‌ی پنجره‌ها بسته‌اند (پنل «اوقات شرعی در دسترس نیست» نشان می‌دهد).
- دریافت از شبکه عمداً خارج از تراکنش دیتابیس انجام می‌شود (handler اول get_today_timings را
  صدا می‌زند و نتیجه را به توابع دیتابیسی می‌دهد).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import PrayerClaim, User
from bot.domain import prayer_times as pt

logger = logging.getLogger(__name__)

API_URL = "https://api.aladhan.com/v1/timings/{date}"
FETCH_TIMEOUT_SECONDS = 10
FAILURE_RETRY_SECONDS = 60

PRAYER_TZ = ZoneInfo(settings.prayer_timezone)

_cache: dict[str, dict[str, datetime]] = {}
_fail_until: float = 0.0
_lock: asyncio.Lock | None = None


def local_day(now: datetime) -> date:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(PRAYER_TZ).date()


async def _fetch_payload(day: date) -> dict | None:
    params = {
        "latitude": str(settings.prayer_latitude),
        "longitude": str(settings.prayer_longitude),
        "method": str(settings.prayer_method),
        "timezonestring": settings.prayer_timezone,
    }
    url = API_URL.format(date=day.strftime("%d-%m-%Y"))
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning("Aladhan status %s", response.status)
                    return None
                return await response.json(content_type=None)
    except Exception:  # noqa: BLE001 — شبکه/JSON/timeout: همه به «در دسترس نیست» ختم می‌شوند
        logger.warning("دریافت اوقات شرعی ناموفق بود", exc_info=True)
        return None


async def get_today_timings(
    now: datetime | None = None, *, fetcher=_fetch_payload
) -> dict[str, datetime] | None:
    """{prayer_key: زمان اذان} برای «امروزِ» شهر تنظیم‌شده؛ None یعنی در دسترس نیست."""
    global _fail_until, _lock
    now = now or datetime.now(timezone.utc)
    day = local_day(now)
    key = day.isoformat()
    if key in _cache:
        return _cache[key]
    if time.monotonic() < _fail_until:
        return None
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if key in _cache:
            return _cache[key]
        payload = await fetcher(day)
        timings = pt.parse_adhan_times(payload, day, PRAYER_TZ) if payload else None
        if timings is None:
            _fail_until = time.monotonic() + FAILURE_RETRY_SECONDS
            return None
        _cache.clear()
        _cache[key] = timings
        return timings


# ---------------------------------------------------------------------------
# نمای پنل و ثبت نماز
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrayerView:
    prayer: pt.PrayerDef
    adhan_at: datetime
    state: pt.WindowState
    claimed: bool


async def _claimed_keys_today(session: AsyncSession, user: User, now: datetime) -> set[str]:
    result = await session.execute(
        select(PrayerClaim.prayer_key).where(
            PrayerClaim.user_id == user.id, PrayerClaim.day == local_day(now).isoformat()
        )
    )
    return set(result.scalars().all())


async def get_prayer_views(
    session: AsyncSession, user: User, now: datetime, timings: dict[str, datetime] | None
) -> list[PrayerView] | None:
    if timings is None:
        return None
    claimed = await _claimed_keys_today(session, user, now)
    local_now = now.astimezone(PRAYER_TZ)
    return [
        PrayerView(
            prayer=prayer,
            adhan_at=timings[prayer.key],
            state=pt.window_state(timings[prayer.key], local_now),
            claimed=prayer.key in claimed,
        )
        for prayer in pt.PRAYERS
    ]


class ClaimResult(Enum):
    SUCCESS = "success"
    TOO_EARLY = "too_early"
    TOO_LATE = "too_late"
    ALREADY_CLAIMED = "already_claimed"
    UNAVAILABLE = "unavailable"
    UNKNOWN_PRAYER = "unknown_prayer"


@dataclass
class ClaimOutcome:
    result: ClaimResult
    prayer: pt.PrayerDef | None = None
    adhan_at: datetime | None = None
    noor_reward: int = 0
    noor_current: int = 0


async def claim_prayer(
    session: AsyncSession,
    user: User,
    prayer_key: str,
    now: datetime,
    timings: dict[str, datetime] | None,
) -> ClaimOutcome:
    prayer = pt.PRAYER_BY_KEY.get(prayer_key)
    if prayer is None:
        return ClaimOutcome(ClaimResult.UNKNOWN_PRAYER)
    if timings is None:
        return ClaimOutcome(ClaimResult.UNAVAILABLE, prayer=prayer)

    adhan_at = timings[prayer.key]
    state = pt.window_state(adhan_at, now.astimezone(PRAYER_TZ))
    if state == pt.WindowState.BEFORE:
        return ClaimOutcome(ClaimResult.TOO_EARLY, prayer=prayer, adhan_at=adhan_at)
    if state == pt.WindowState.AFTER:
        return ClaimOutcome(ClaimResult.TOO_LATE, prayer=prayer, adhan_at=adhan_at)

    if prayer.key in await _claimed_keys_today(session, user, now):
        return ClaimOutcome(ClaimResult.ALREADY_CLAIMED, prayer=prayer, adhan_at=adhan_at)

    session.add(
        PrayerClaim(
            user_id=user.id,
            prayer_key=prayer.key,
            day=local_day(now).isoformat(),
            claimed_at=now,
            noor_reward=pt.PRAYER_NOOR_REWARD,
        )
    )
    user.noor_current += pt.PRAYER_NOOR_REWARD
    user.noor_total_earned += pt.PRAYER_NOOR_REWARD
    await session.flush()
    return ClaimOutcome(
        ClaimResult.SUCCESS,
        prayer=prayer,
        adhan_at=adhan_at,
        noor_reward=pt.PRAYER_NOOR_REWARD,
        noor_current=user.noor_current,
    )
