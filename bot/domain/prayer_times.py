"""
منطق خالص «نماز اول وقت» در پنل مسیر انتظار (بدون دیتابیس و بدون شبکه؛ قابل تست مستقیم).

قاعده: دکمه‌ی هر نماز همیشه در پنل نمایش داده می‌شود، ولی فقط از لحظه‌ی اذانِ همان نماز تا
PRAYER_WINDOW_MINUTES دقیقه بعد از آن قابل ثبت است.

  صبح         -> اذان صبح (Fajr)
  ظهر و عصر   -> اذان ظهر (Dhuhr)
  مغرب و عشا  -> اذان مغرب (Maghrib)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

PRAYER_WINDOW_MINUTES = 30
PRAYER_NOOR_REWARD = 10  # نور هر ثبت «نماز اول وقت» (روزی یک بار برای هر نماز)


@dataclass(frozen=True)
class PrayerDef:
    key: str  # شناسه‌ی پایدار (در دیتابیس و callback_data)
    label: str  # نام نمایشی روی دکمه
    api_key: str  # نام وقت در پاسخ Aladhan
    confirm_label: str  # متن دکمه‌ی تأیید داخل پنجره
    emoji: str


PRAYERS: tuple[PrayerDef, ...] = (
    PrayerDef("subh", "نماز صبح", "Fajr", "نماز صبح رو اول وقت خواندم", "🌅"),
    PrayerDef("zuhrayn", "نماز ظهر و عصر", "Dhuhr", "نماز ظهر و عصر رو اول وقت خواندم", "☀️"),
    PrayerDef("maghribayn", "نماز مغرب و عشا", "Maghrib", "نماز مغرب و عشا رو اول وقت خواندم", "🌇"),
)
PRAYER_BY_KEY: dict[str, PrayerDef] = {p.key: p for p in PRAYERS}


class WindowState(Enum):
    BEFORE = "before"  # هنوز اذان نشده
    OPEN = "open"  # داخل ۳۰ دقیقه‌ی بعد از اذان
    AFTER = "after"  # پنجره بسته شد


_HHMM = re.compile(r"(\d{1,2}):(\d{2})")


def parse_adhan_times(payload: dict, day: date, tz: ZoneInfo) -> dict[str, datetime] | None:
    """
    پاسخ JSON ‌ی Aladhan (endpoint /timings/{date}) -> {prayer_key: زمان اذان با tz}.
    اگر ساختار پاسخ معتبر نبود یا یکی از سه وقت لازم نبود، None.
    """
    try:
        timings = payload["data"]["timings"]
    except (KeyError, TypeError):
        return None
    if not isinstance(timings, dict):
        return None
    result: dict[str, datetime] = {}
    for prayer in PRAYERS:
        raw = timings.get(prayer.api_key)
        match = _HHMM.search(raw) if isinstance(raw, str) else None
        if match is None:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        result[prayer.key] = datetime.combine(day, time(hour, minute), tzinfo=tz)
    return result


def window_end(adhan_at: datetime) -> datetime:
    return adhan_at + timedelta(minutes=PRAYER_WINDOW_MINUTES)


def window_state(adhan_at: datetime, now: datetime) -> WindowState:
    if now < adhan_at:
        return WindowState.BEFORE
    if now < window_end(adhan_at):
        return WindowState.OPEN
    return WindowState.AFTER


def format_hhmm(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"
