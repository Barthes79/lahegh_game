"""
سرویس «نماز اول وقت»: گرفتن اوقات شرعی از Aladhan API (با کش روزانه) و ثبت «نماز اول وقت خواندم».

- اوقات هر شهر در هر روز فقط یک بار گرفته و در حافظه کش می‌شود. اگر API برای یک شهر خطا بدهد،
  ۶۰ ثانیه برای همان شهر دوباره تلاش نمی‌شود و تا آن موقع پنجره‌هایش بسته‌اند
  (پنل «اوقات شرعی در دسترس نیست» نشان می‌دهد).
- شهر هر کاربر در users.prayer_city ذخیره می‌شود (domain/cities_data.py)؛ بدون انتخاب، شهر پیش‌فرض
  سرور (PRAYER_* در .env) استفاده می‌شود.
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
from bot.domain.cities_data import CITIES, City, get_city

logger = logging.getLogger(__name__)

API_URL = "https://api.aladhan.com/v1/timings/{date}"
FETCH_TIMEOUT_SECONDS = 10
FAILURE_RETRY_SECONDS = 60

_cache: dict[tuple[str, str], dict[str, datetime]] = {}  # (city_key, YYYY-MM-DD) -> اوقات
_fail_until: dict[str, float] = {}  # city_key -> زمان (monotonic) تا آن موقع دوباره تلاش نکن
_locks: dict[str, asyncio.Lock] = {}


def default_city() -> City:
    """
    شهر پیش‌فرض (برای کاربری که شهری انتخاب نکرده): تنظیمات PRAYER_* سرور.
    اگر مختصات تنظیم‌شده با یکی از شهرهای لیست یکی باشد (مثل پیش‌فرض: تهران)، همان شهر
    با نام و کلیدش برگردانده می‌شود تا در فهرست انتخاب هم ✅ بگیرد.
    """
    for city in CITIES:
        if (
            abs(city.latitude - settings.prayer_latitude) < 0.01
            and abs(city.longitude - settings.prayer_longitude) < 0.01
            and city.timezone == settings.prayer_timezone
        ):
            return city
    return City(
        key="default",
        name="پیش‌فرض ربات",
        latitude=settings.prayer_latitude,
        longitude=settings.prayer_longitude,
        timezone=settings.prayer_timezone,
    )


def city_for_user(user: User | None) -> City:
    return (get_city(user.prayer_city) if user is not None else None) or default_city()


def local_day(now: datetime, tz: ZoneInfo) -> date:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(tz).date()


def _tz_of(timings: dict[str, datetime]) -> ZoneInfo:
    """منطقه‌ی زمانی شهر از خود زمان‌های اذان (parse_adhan_times با tz شهر ساخته)."""
    return next(iter(timings.values())).tzinfo  # type: ignore[return-value]


async def _fetch_payload(day: date, city: City) -> dict | None:
    params = {
        "latitude": str(city.latitude),
        "longitude": str(city.longitude),
        "method": str(settings.prayer_method),
        "timezonestring": city.timezone,
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
    now: datetime | None = None, city: City | None = None, *, fetcher=_fetch_payload
) -> dict[str, datetime] | None:
    """{prayer_key: زمان اذان} برای «امروزِ» شهر داده‌شده؛ None یعنی در دسترس نیست."""
    now = now or datetime.now(timezone.utc)
    city = city or default_city()
    tz = ZoneInfo(city.timezone)
    day = local_day(now, tz)
    key = (city.key, day.isoformat())
    if key in _cache:
        return _cache[key]
    if time.monotonic() < _fail_until.get(city.key, 0.0):
        return None
    lock = _locks.setdefault(city.key, asyncio.Lock())
    async with lock:
        if key in _cache:
            return _cache[key]
        payload = await fetcher(day, city)
        timings = pt.parse_adhan_times(payload, day, tz) if payload else None
        if timings is None:
            _fail_until[city.key] = time.monotonic() + FAILURE_RETRY_SECONDS
            return None
        # فقط اوقات امروز نگه داشته می‌شود (کش روزهای قبل پاک می‌شود).
        for old in [k for k in _cache if k[1] != key[1]]:
            del _cache[old]
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


async def _claimed_keys_today(
    session: AsyncSession, user: User, now: datetime, tz: ZoneInfo
) -> set[str]:
    result = await session.execute(
        select(PrayerClaim.prayer_key).where(
            PrayerClaim.user_id == user.id, PrayerClaim.day == local_day(now, tz).isoformat()
        )
    )
    return set(result.scalars().all())


async def get_prayer_views(
    session: AsyncSession, user: User, now: datetime, timings: dict[str, datetime] | None
) -> list[PrayerView] | None:
    if timings is None:
        return None
    tz = _tz_of(timings)
    claimed = await _claimed_keys_today(session, user, now, tz)
    local_now = now.astimezone(tz)
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

    tz = _tz_of(timings)
    adhan_at = timings[prayer.key]
    state = pt.window_state(adhan_at, now.astimezone(tz))
    if state == pt.WindowState.BEFORE:
        return ClaimOutcome(ClaimResult.TOO_EARLY, prayer=prayer, adhan_at=adhan_at)
    if state == pt.WindowState.AFTER:
        return ClaimOutcome(ClaimResult.TOO_LATE, prayer=prayer, adhan_at=adhan_at)

    if prayer.key in await _claimed_keys_today(session, user, now, tz):
        return ClaimOutcome(ClaimResult.ALREADY_CLAIMED, prayer=prayer, adhan_at=adhan_at)

    session.add(
        PrayerClaim(
            user_id=user.id,
            prayer_key=prayer.key,
            day=local_day(now, tz).isoformat(),
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
