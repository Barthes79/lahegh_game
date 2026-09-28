"""
منطق «حلقه ذکر» (Level 2، ویژگی دوم).

نکات کلیدی طراحی (طبق سند نهایی):
- حلقه به هیچ تعداد عضوی محدود نیست؛ ۵ نفر فقط شرط فعال‌شدن milestone روزانه است، نه
  شرط ساخت/فعال بودن خود حلقه.
- سهم روزانه‌ی هر عضو ۱۰ ذکر معتبر است (صلوات/نامعتبر/cooldown حساب نمی‌شود).
- هر ذکر معتبر عضو (فقط تا سقف ۱۰امین ذکر روز) پاداش معمول + ۲ نور bonus حلقه می‌دهد؛
  این یک پاداش واحد است، نه دو پرداخت جدا.
- وقتی در یک روز مشخص، ۵ عضو مختلف هرکدام ۱۰/۱۰ کامل کنند، ۵۰ نور (۱۰ برای هرکدام)
  فقط یک‌بار در همان روز پرداخت می‌شود؛ ۵ نفر «زودتر تکمیل‌کننده» معیار انتخاب‌اند.
- عضویت/خروج/حذف: هر کاربر فقط در یک حلقه، و ۷۲ ساعت قفل بعد از پیوستن.
"""
from __future__ import annotations

from datetime import timedelta

# سهم روزانه‌ی هر عضو
CIRCLE_DAILY_TARGET = 10

# پاداش bonus حلقه روی هر ذکر معتبر عضو، فقط تا سقف CIRCLE_DAILY_TARGET ذکر در روز
CIRCLE_DHIKR_NOOR_BOOST = 0

# پاداش شخصی پس از تکمیل ۱۰ ذکر روزانه
CIRCLE_PERSONAL_REWARD_NOOR = 25

# شرط milestone پنج‌نفره
CIRCLE_MILESTONE_MIN_MEMBERS = 5
CIRCLE_MILESTONE_REWARD_PER_MEMBER = 15
CIRCLE_MILESTONE_TOTAL_NOOR = CIRCLE_MILESTONE_REWARD_PER_MEMBER * CIRCLE_MILESTONE_MIN_MEMBERS

# قفل خروج/حذف عضو بعد از پیوستن
CIRCLE_MEMBERSHIP_LOCK = timedelta(0)

# پنجره سهم هر کاربر از اولین ذکر حلقه خودش شروع می‌شود.
CIRCLE_USER_QUOTA_WINDOW = timedelta(hours=24)
# عمر هر حلقه از اولین ذکر ثبت‌شده در آن شروع می‌شود.
CIRCLE_LIFETIME = timedelta(hours=24)

# کولداون مستقلِ ذکرهای ویژه‌ی «حلقه ذکر» (۵ ذکر CIRCLE_DISPLAY_DHIKR_KEYS)،
# کاملاً جدا از کولداون ذکر عادی. مقدار فعلی برای تست سریع ۱ ثانیه است.
CIRCLE_DHIKR_COOLDOWN_SECONDS = 1

# وضعیت‌های عضویت
MEMBER_STATUS_ACTIVE = "active"
MEMBER_STATUS_LEFT = "left"

LEAVE_REASON_SELF = "self_left"
LEAVE_REASON_REMOVED = "removed_by_creator"


def can_leave_or_be_removed(joined_at, now) -> bool:
    """خروج/حذف عضو همیشه مجاز است؛ cooldown عضویت حذف شده است."""
    return True
