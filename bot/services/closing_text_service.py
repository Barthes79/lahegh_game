"""
انتخاب تصادفی «متن پایانی» برای پیام موفقیت عادی صلوات/ذکر (طبق درخواست کاربر).

فقط برای پیام موفقیت عادی استفاده می‌شود (نه milestone/level-up/PV/صندوقچه).
برای جلوگیری از تکرار آزاردهنده، ۱۰ متن آخرِ هر کاربر در حافظه (نه دیتابیس) نگه داشته
می‌شود و تا حد امکان تکرار نمی‌شوند. فعلاً یک مجموعه‌ی مشترک برای صلوات و ذکر است.
"""
from __future__ import annotations

import random
from collections import defaultdict, deque

from bot.texts.messages import CLOSING_LINES

_RECENT_HISTORY_SIZE = 10

_recent_by_user: dict[int, deque[str]] = defaultdict(lambda: deque(maxlen=_RECENT_HISTORY_SIZE))


def pick_closing_line(telegram_id: int) -> str:
    """یک متن تصادفی از CLOSING_LINES انتخاب می‌کند که در ۱۰ متن اخیر همین کاربر نباشد."""
    history = _recent_by_user[telegram_id]
    candidates = [line for line in CLOSING_LINES if line not in history]
    if not candidates:
        # اگر (نظری) همه‌ی مجموعه در تاریخچه بود، محدودیت برداشته می‌شود تا انتخاب متوقف نشود.
        candidates = list(CLOSING_LINES)
    choice = random.choice(candidates)
    history.append(choice)
    return choice
