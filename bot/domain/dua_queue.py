"""
منطق «التماس دعا» (Level 2، ویژگی اول؛ نام داخلی: dua_queue).

اعداد این ماژول دقیقاً طبق تصمیم‌های تأییدشده‌ی طراح بازی هستند:
- سهمیه‌ی روزانه‌ی ذکر برای باز شدن پنل: ۱۰ (هر ذکر معتبر غیر از ذکر حلقه؛ صلوات حساب نمی‌شود).
- محدودیت حداقل عضو فعال گروه حذف شده است (طبق تصمیم طراح: تعداد اعضای گروه مهم نیست).
- هر پنل حداکثر ۵ پاسخ (هر کاربر فقط یک‌بار) یا حداکثر ۱۲ ساعت عمر — هرکدام زودتر برسد.
  با رسیدن به پنجمین پاسخ، پنل بسته می‌شود.
- هر کاربر فقط هر ۲۴ ساعت یک پنل می‌تواند بسازد.
- پاداش پاسخ‌دهنده: فقط پاداش عادیِ همان ذکر (۱۰ نور)، بدون بوست اضافه.
- پاداش صاحب پنل: ۱۵ نور به‌ازای هر پاسخ معتبر + ۲۵ نور بونوس وقتی پنجمین پاسخ ثبت شد.
- پاسخ‌دهنده باید متن ذکر نمایش‌داده‌شده روی پنل را (با همان normalization اذکار) روی خودِ
  پیام پنل ریپلای کند.

مبنای «روز» برای سهمیه‌ی روزانه: Asia/Tehran (طبق تأیید طراح)، ریست ساعت ۰۰:۰۰.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# ---------------------------------------------------------------------------
# سهمیه‌ی روزانه‌ی ذکر رایگان (شرط باز شدن صف دعا برای همان روز)
# ---------------------------------------------------------------------------

DAILY_FREE_DHIKR_REQUIRED = 10


def tehran_date_str(dt: datetime) -> str:
    """تاریخ (YYYY-MM-DD) بر مبنای ساعت تهران، برای تشخیص «همان روز»."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TEHRAN_TZ).date().isoformat()


# ---------------------------------------------------------------------------
# شرایط ساخت صف
# ---------------------------------------------------------------------------

QUEUE_OWNER_COOLDOWN = timedelta(hours=24)

# ---------------------------------------------------------------------------
# عمر و ظرفیت صف
# ---------------------------------------------------------------------------

QUEUE_MAX_ANSWERS = 5
QUEUE_LIFETIME = timedelta(hours=12)

# ---------------------------------------------------------------------------
# پاداش‌ها
# ---------------------------------------------------------------------------

# نور صاحب پنل به‌ازای هر پاسخ معتبر.
QUEUE_OWNER_REWARD_PER_ANSWER = 15

# بونوس یک‌باره‌ی صاحب پنل وقتی پنل به سقف پاسخ‌ها (۵ نفر) رسید.
QUEUE_OWNER_COMPLETION_BONUS = 25


def compute_expiry(created_at: datetime) -> datetime:
    return created_at + QUEUE_LIFETIME


def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now >= expires_at


def is_queue_open(*, closed: bool, answers_count: int, expires_at: datetime, now: datetime | None = None) -> bool:
    """آیا صف هنوز باز است؟ (نه بسته‌شده، نه پر، نه منقضی)."""
    if closed:
        return False
    if answers_count >= QUEUE_MAX_ANSWERS:
        return False
    if is_expired(expires_at, now):
        return False
    return True
