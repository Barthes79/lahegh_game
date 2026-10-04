"""
تنظیمات مرکزی پروژه.
همه‌ی مقادیر قابل‌تنظیم (توکن، مسیر دیتابیس، تایمینگ‌های یادآوری و ...) از اینجا خوانده می‌شوند
تا در آینده بدون دست‌زدن به منطق برنامه، قابل تغییر باشند.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _get_str(name: str, default: str) -> str:
    val = os.getenv(name)
    return default if val is None or val.strip() == "" else val.strip()


def _get_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "laahiq.db"))
    admin_ids: set[int] = field(default_factory=_get_admin_ids)

    # یادآوری غیرفعالی (بخش ۱۷ سند)
    reminder_inactivity_hours: int = field(
        default_factory=lambda: _get_int("REMINDER_INACTIVITY_HOURS", 12)
    )
    reminder_min_gap_hours: int = field(
        default_factory=lambda: _get_int("REMINDER_MIN_GAP_HOURS", 24)
    )
    reminder_check_interval_minutes: int = field(
        default_factory=lambda: _get_int("REMINDER_CHECK_INTERVAL_MINUTES", 30)
    )

    # --- مسیر انتظار: اوقات شرعی (Aladhan API) ---
    # پیش‌فرض: تهران، روش ۷ (مؤسسه ژئوفیزیک دانشگاه تهران). همه از .env قابل تغییرند.
    prayer_latitude: float = field(default_factory=lambda: _get_float("PRAYER_LATITUDE", 35.6892))
    prayer_longitude: float = field(default_factory=lambda: _get_float("PRAYER_LONGITUDE", 51.3890))
    prayer_method: int = field(default_factory=lambda: _get_int("PRAYER_METHOD", 7))
    prayer_timezone: str = field(default_factory=lambda: _get_str("PRAYER_TIMEZONE", "Asia/Tehran"))

    # لینک پست صوتی درس ۱ در کانال عمومی (Copy Post Link)؛ خالی = ارسال فایل جدا مثل قبل
    lesson1_audio_url: str = field(default_factory=lambda: _get_str("LESSON_1_AUDIO_URL", ""))
    lesson2_audio_url: str = field(
        default_factory=lambda: _get_str("LESSON_2_AUDIO_URL", "https://t.me/dsfgnsdfhre/4")
    )


settings = Settings()
