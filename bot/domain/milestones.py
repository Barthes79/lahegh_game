"""
Milestoneهای Level 1 (بخش ۱۱) و متن دستورات ثابت بازی.
"""
from __future__ import annotations

MILESTONE_BANK_AZKAR = 3
MILESTONE_NAMEH_AMAL = 6
MILESTONE_TASBIH = 9
MILESTONE_LEVEL_UP = 13  # صلوات سیزدهم: انتقال از سطح ۱ به سطح ۲

# دستورات متنی ثابت بازی (بخش ۱۳، ۱۴، ۱۵)
COMMAND_BANK_AZKAR = "بانک اذکار"
COMMAND_NAMEH_AMAL = "نامه اعمالم"
COMMAND_TASBIH = "تسبیح"

# Level 2: التماس دعا (نام داخلی: dua_queue) — بر خلاف بانک اذکار/تسبیح/نامه اعمالم، این دستور فقط در
# گروه معنا دارد (چون به chat_id و اعضای فعال همان گروه وابسته است)؛ در PV نادیده گرفته می‌شود.
COMMAND_DUA_QUEUE = "التماس دعا"

# Level 2: حلقه ذکر — مثل صف دعا، در گروه و PV هر دو معنا دارد (پنل شخصی کاربر است).
COMMAND_DHIKR_CIRCLE = "حلقه ذکر"

GAME_TRIGGER_COMMANDS = {
    COMMAND_BANK_AZKAR,
    COMMAND_NAMEH_AMAL,
    COMMAND_TASBIH,
    COMMAND_DUA_QUEUE,
    COMMAND_DHIKR_CIRCLE,
}
