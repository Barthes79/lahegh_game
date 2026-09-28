"""
صفحات بازی: «بانک اذکار» (بخش ۱۳)، «نامه اعمالم» (بخش ۱۴)، «تسبیح» (بخش ۱۵).

طبق اصلاحات نهایی: /start هیچ نقشی در شروع بازی ندارد — شروع بازی فقط با
اولین صلوات معتبر در گروه اتفاق می‌افتد (در bot/services/activity_service.py).

دیپ‌لینک دعوت حلقه ذکر (t.me/<bot>?start=circle_join_<id>) هم دیگر پشتیبانی
نمی‌شود؛ دعوت به حلقه فقط با Reply در گروه انجام می‌شود (bot/handlers/dhikr_circle.py).

طبق بخش ۱۲ سند اصلی: قابلیت قفل‌شده نباید لو برود — اگر کاربر دستور یک قابلیت
هنوز-قفل را بفرستد، به‌سادگی نادیده گرفته می‌شود (بدون پاسخ).
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import FSInputFile, Message
from sqlalchemy import func, select

from bot.database.engine import async_session_factory
from bot.domain.dhikr_data import DHIKR_LIST
from bot.domain.salawat_data import LEVEL_2_REQUIRED_SALAWAT
from bot.domain.tasbih_data import get_dhikr_cooldown_for_level
from bot.keyboards.inline import (
    bank_azkar_main_keyboard,
    tasbih_panel_main_keyboard,
)
from bot.services.unlock_service import is_unlocked
from bot.services.user_service import get_user_by_telegram_id
from bot.texts import messages as texts
from bot.utils.assets import BANK_AZKAR_PHOTO_PATH, TASBIH_PHOTO_PATH

router = Router(name="commands")


# ---------------------------------------------------------------------------
# /start — طبق قانون اصلی پروژه، /start هیچ نقشی در *شروع بازی* ندارد.
# نه دیپ‌لینک دعوت به حلقه دیگر پشتیبانی می‌شود و نه هیچ payload دیگری.
# هر /start (با هر payload) کاملاً بی‌صدا نادیده گرفته می‌شود.
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    return


# ---------------------------------------------------------------------------
# ابزار تبدیل اعداد و تاریخ شمسی
# ---------------------------------------------------------------------------


def to_persian_digits(value: str) -> str:
    """
    تبدیل اعداد انگلیسی به اعداد فارسی.
    """
    translation = str.maketrans(
        "0123456789",
        "۰۱۲۳۴۵۶۷۸۹",
    )
    return str(value).translate(translation)


def format_shamsi_datetime(dt) -> str:
    """
    تبدیل datetime میلادی به تاریخ و ساعت شمسی.

    game_started_at در دیتابیس بر اساس UTC ذخیره می‌شود.
    ممکن است SQLAlchemy آن را به صورت timezone-aware یا naive برگرداند.
    در هر دو حالت، ابتدا زمان را به UTC نسبت می‌دهیم و سپس به
    ساعت تهران تبدیل می‌کنیم.

    خروجی نمونه:
    ۳ مهر ۱۴۰۵ — ساعت ۱۴:۳۲
    """
    import jdatetime

    utc = ZoneInfo("UTC")
    tehran = ZoneInfo("Asia/Tehran")

    # اگر datetime بدون timezone از SQLite برگردد،
    # فرض می‌کنیم مقدار ذخیره‌شده UTC است.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=utc)

    # تبدیل UTC به ساعت تهران
    dt = dt.astimezone(tehran)

    jalali_date = jdatetime.datetime.fromgregorian(
        datetime=dt
    )

    month_names = [
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ]

    result = (
        f"{jalali_date.day} "
        f"{month_names[jalali_date.month - 1]} "
        f"{jalali_date.year} — "
        f"ساعت {jalali_date.hour:02d}:{jalali_date.minute:02d}"
    )

    return to_persian_digits(result)


# ---------------------------------------------------------------------------
# پنل «بانک اذکار»
# ---------------------------------------------------------------------------


async def show_bank_azkar(message: Message) -> None:
    """
    پنل «بانک اذکار» — یک پیام واحد با دکمه برای هر ذکر (نه چند پیام جدا).

    هر بار کاربر «بانک اذکار» را بفرستد، یک پنل مستقل و جدید ساخته می‌شود؛
    پنل‌های قبلی دست‌نخورده باقی می‌مانند.

    نور فعلی کاربر در پنل نشان داده نمی‌شود.
    """
    if message.from_user is None:
        return

    owner_id = message.from_user.id

    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(
            session,
            owner_id,
        )

        if user is None or not user.bank_azkar_unlocked:
            return  # قابلیت هنوز باز نشده -> نادیده بگیر (بخش ۱۲)

        unlocked_map = {
            dhikr.key: await is_unlocked(
                session,
                user,
                dhikr,
            )
            for dhikr in DHIKR_LIST
        }

    await message.reply_photo(
        FSInputFile(BANK_AZKAR_PHOTO_PATH),
        caption=texts.bank_azkar_panel_header(),
        reply_markup=bank_azkar_main_keyboard(
            owner_id,
            DHIKR_LIST,
            unlocked_map,
        ),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# «نامه اعمالم»
# ---------------------------------------------------------------------------


async def show_nameh_amal(message: Message) -> None:
    """
    نمایش «نامه اعمالم».

    تاریخ شروع پیشرفت معنویت از game_started_at گرفته می‌شود؛
    این مقدار دقیقاً در اولین صلوات معتبر ثبت شده است.

    تاریخ به شمسی و با اعداد فارسی نمایش داده می‌شود
    و ساعت نیز در همان خط کنار تاریخ قرار می‌گیرد.
    """
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(
            session,
            message.from_user.id,
        )

        if user is None or not user.nameh_amal_unlocked:
            return

        from bot.database.models import DhikrUnlock

        result = await session.execute(
            select(func.count())
            .select_from(DhikrUnlock)
            .where(
                DhikrUnlock.user_id == user.id
            )
        )

        dhikr_unlocked_count = result.scalar_one() or 0

        # الحمدلله رایگان است و بدون رکورد unlock هم فعال محسوب می‌شود
        dhikr_unlocked_count += 1

        # تاریخ و ساعت شروع پیشرفت معنویت
        # game_started_at در اولین صلوات معتبر ثبت شده است.
        if user.game_started_at:
            start_date_str = format_shamsi_datetime(
                user.game_started_at
            )
        else:
            start_date_str = "-"

        # این مقدار فعلاً برای سازگاری با تابع nameh_amal نگه داشته شده است.
        last_activity_str = (
            user.last_activity_at.strftime(
                "%Y-%m-%d %H:%M"
            )
            if user.last_activity_at
            else "-"
        )

        text = texts.nameh_amal(
            start_date_str=start_date_str,
            level=user.level,
            salawat_progress=user.level_progress,
            salawat_progress_total=(LEVEL_2_REQUIRED_SALAWAT if user.level >= 2 else 12),
            salawat_count=user.salawat_count,
            dhikr_count=user.dhikr_count,
            noor_current=user.noor_current,
            noor_total_earned=user.noor_total_earned,
            chest_count=user.chest_count,
            tasbih_level=user.tasbih_level,
            tasbih_unlocked=user.tasbih_unlocked,
            dhikr_unlocked_count=dhikr_unlocked_count,
            total_activities=user.total_activities,
            last_activity_str=last_activity_str,
        )

        await message.reply(text)


# ---------------------------------------------------------------------------
# پنل «تسبیح»
# ---------------------------------------------------------------------------


async def show_tasbih(message: Message) -> None:
    """
    پنل «تسبیح» — مثل پنل بانک اذکار: یک پیام واحد (عکس + کپشن)
    که owner_id در callback_data تمام دکمه‌هایش کدگذاری شده
    (bot/handlers/tasbih_panel.py).

    هر بار کاربر «تسبیح» را بفرستد، یک پنل مستقل و جدید ساخته می‌شود.
    """
    if message.from_user is None:
        return

    owner_id = message.from_user.id

    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(
            session,
            owner_id,
        )

        if user is None or not user.tasbih_unlocked:
            return  # قابلیت هنوز باز نشده -> نادیده بگیر (بخش ۱۲)

        # اینجا cooldown سطح فعلی تسبیح نمایش داده می‌شود
        # (نه مقدار فریزشده‌ی آخرین ذکر)
        cooldown = get_dhikr_cooldown_for_level(
            user.tasbih_level
        )

        level = user.tasbih_level

    await message.reply_photo(
        FSInputFile(TASBIH_PHOTO_PATH),
        caption=texts.tasbih_panel_header(
            level,
            cooldown,
        ),
        reply_markup=tasbih_panel_main_keyboard(
            owner_id,
            level,
        ),
        parse_mode="Markdown",
    )
