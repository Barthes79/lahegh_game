"""
Milestoneهای Level 1 (بخش ۱۱) و متن دستورات ثابت بازی.
"""
from __future__ import annotations

# سطح ۱ پنج ذکر دارد (بانک اذکار حذف شده). نامه اعمال با ذکر ۳، تسبیح و پایان سطح با ذکر ۵.
# ورود به سطح ۲ با ذکرِ بعد از ۵/۵ و فقط بعد از قبولی آزمون درس ۱ («مسیر انتظار») انجام می‌شود.
MILESTONE_NAMEH_AMAL = 3
MILESTONE_TASBIH = 5
# انتقال از سطح ۲ به ۳: وقتی پیشرفت سطح ۲ به ۲۴/۲۴ رسیده باشد، صلواتِ بعدی کاربر را وارد
# سطح ۳ می‌کند (milestone_kind = "level_up_3").
MILESTONE_LEVEL_UP_3 = "level_up_3"

# دستورات متنی ثابت بازی (بخش ۱۳، ۱۴، ۱۵)
# سطح ۱: پنل «مسیر انتظار» (جایگزین بانک اذکار) — نماز اول وقت، دروس و آزمون
COMMAND_PATH = "مسیر انتظار"
COMMAND_NAMEH_AMAL = "نامه اعمالم"
COMMAND_TASBIH = "تسبیح"

# Level 2: التماس دعا (نام داخلی: dua_queue) — بر خلاف بانک اذکار/تسبیح/نامه اعمالم، این دستور فقط در
# گروه معنا دارد (چون به chat_id و اعضای فعال همان گروه وابسته است)؛ در PV نادیده گرفته می‌شود.
COMMAND_DUA_QUEUE = "التماس دعا"

# Level 2: حلقه ذکر — مثل صف دعا، در گروه و PV هر دو معنا دارد (پنل شخصی کاربر است).
COMMAND_DHIKR_CIRCLE = "حلقه ذکر"

# Level 3: مشاغل و فروشگاه — پنل شخصی کاربر؛ در گروه و PV هر دو معنا دارد.
COMMAND_JOB = "شغل"
COMMAND_JOB_ALIAS = "شغل من"
COMMAND_STORE = "فروشگاه"
COMMAND_MARKET = "مارکت"  # نام قدیمی؛ همان فروشگاه است
COMMAND_WAREHOUSE = "انبار"
COMMAND_BANK = "بانک"

GAME_TRIGGER_COMMANDS = {
    COMMAND_PATH,
    COMMAND_NAMEH_AMAL,
    COMMAND_TASBIH,
    COMMAND_DUA_QUEUE,
    COMMAND_DHIKR_CIRCLE,
    COMMAND_JOB,
    COMMAND_JOB_ALIAS,
    COMMAND_STORE,
    COMMAND_MARKET,
    COMMAND_WAREHOUSE,
    COMMAND_BANK,
}
