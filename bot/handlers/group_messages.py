"""
هندلر اصلی پیام‌های متنی: صلوات، ذکر، و دستورات بازی
(بانک اذکار / نامه اعمالم / تسبیح).

طبق اصلاحات نهایی:
- فعالیت (صلوات/ذکر) فقط داخل گروه ثبت می‌شود؛ پیام‌های PV هرگز فعالیت محسوب نمی‌شوند.
- هر فعالیت موفق دقیقاً یک نتیجه دارد: یا پیام/توضیح گروهی، یا نتیجه در PV — هرگز هر دو با هم.
- ۶۷٪ (غیر از اولین‌بار): فقط reaction در گروه + نتیجه‌ی فعالیت بلافاصله در PV کاربر.
- ۶۷٪ (اولین‌بار که کاربر reaction می‌گیرد):
  reaction + یک توضیح گروهی که خودش نتیجه‌ی واقعی فعالیت
  (نور، نور معنویتت، Progress) را هم نشان می‌دهد.
  در این حالت PV فرستاده نمی‌شود.
- ۳۳٪ یا صلوات‌های Milestone (۳/۶/۹/۱۲) یا اولین صلوات:
  پیام کامل در گروه، بدون هیچ پیام PV.
- شکست فنی reaction:
  پیام کامل در گروه، بدون PV.
- صندوقچه همیشه در گروه فرستاده می‌شود؛ این یک رویداد جدا از
  «نتیجه‌ی فعالیت» است، نه بخشی از آن.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.types import Message, ReactionTypeEmoji, Update

from bot.database.engine import async_session_factory
from bot.domain import dhikr_circle as circle_domain
from bot.domain import closing_lines
from bot.domain.milestones import (
    COMMAND_BANK_AZKAR,
    COMMAND_DHIKR_CIRCLE,
    COMMAND_DUA_QUEUE,
    COMMAND_JOB,
    COMMAND_JOB_ALIAS,
    COMMAND_MARKET,
    COMMAND_STORE,
    COMMAND_BANK,
    COMMAND_NAMEH_AMAL,
    COMMAND_TASBIH,
    COMMAND_WAREHOUSE,
    MILESTONE_LEVEL_UP_3,
)
from bot.domain.normalization import normalize_text
from bot.domain.validator import ActivityKind
from bot.keyboards.inline import chest_open_button, dhikr_unlock_button
from bot.services.user_service import get_or_create_user
from bot.services.activity_service import (
    ActivityOutcome,
    OutcomeStatus,
    process_activity,
)
from bot.domain import jobs_data as jobs_domain
from bot.texts import job_texts
from bot.texts import messages as texts
from bot.utils.persian_format import render_progress_bar

logger = logging.getLogger(__name__)

router = Router(name="group_messages")


# ---------------------------------------------------------------------------
# تشخیص نوع چت
# ---------------------------------------------------------------------------


def _chat_allows_activity(chat_type: str) -> bool:
    """
    فقط گروه/سوپرگروه فعالیت بازی محسوب می‌شوند.

    پیام‌های PV هیچ‌وقت صلوات/ذکر را ثبت نمی‌کنند.
    """
    return chat_type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    )


# ---------------------------------------------------------------------------
# میان‌بر تست سطح‌ها (موقت)
# ---------------------------------------------------------------------------

_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _parse_test_level_command(normalized: str) -> int | None:
    """«سطح 1» / «سطح ۲» / «سطح 3» -> عدد سطح؛ در غیر این صورت None."""
    text = normalized.translate(_DIGIT_TRANSLATION)
    if text in ("سطح 1", "سطح 2", "سطح 3"):
        return int(text.split()[1])
    return None


def _apply_test_level(user, level: int) -> None:
    """
    کاربر را برای تست مستقیم وارد یک سطح می‌کند، با وضعیتی که در بازی واقعی هم
    در ابتدای همان سطح دیده می‌شد:

    - سطح ۱: شروع تازه‌ی سطح ۱ (پیشرفت ۱/۱۲)؛ قابلیت‌های سطح ۱ (بانک اذکار، نامه اعمال،
      تسبیح) قفل می‌شوند تا milestoneهای ۳/۶/۹ دوباره قابل تست باشند.
    - سطح ۲: پیشرفت ۱/۲۴؛ قابلیت‌های سطح ۱ باز هستند (چون کاربر واقعی از سطح ۱ گذشته).
    - سطح ۳: پیشرفت ۱/۳۶؛ قابلیت‌های سطح ۱ باز و نور برای تست شغل/ابزار حداقل ۵۰۰۰.

    نور، شغل، تومان و بقیه‌ی داده‌ها دست‌نخورده می‌مانند (به‌جز نور در سطح ۳).
    """
    from datetime import datetime, timezone

    # بدون این، اولین صلوات کاربر «اولین فعالیت» حساب می‌شود و سطح را به ۱ برمی‌گرداند.
    if not user.game_started:
        user.game_started = True
    if user.game_started_at is None:
        user.game_started_at = datetime.now(timezone.utc)

    user.level = level
    user.level_progress = 1

    if level == 1:
        # صلوات ۱ سطح ۱ ثبت شده فرض می‌شود؛ صلوات سیزدهم دوباره به سطح ۲ می‌برد.
        user.salawat_count = 1
        user.bank_azkar_unlocked = False
        user.nameh_amal_unlocked = False
        user.tasbih_unlocked = False
        user.tasbih_level = 0
        return

    # سطح ۲ و ۳: قابلیت‌های سطح ۱ باز هستند.
    user.bank_azkar_unlocked = True
    user.nameh_amal_unlocked = True
    user.tasbih_unlocked = True
    if user.tasbih_level < 1:
        user.tasbih_level = 1

    if level == 2:
        # صلوات سیزدهم اولین صلوات سطح ۲ است.
        user.salawat_count = 13
    elif level == 3:
        # برای تست شغل/ابزار: اگر نور کم بود تا ۵۰۰۰ پر می‌شود.
        if user.noor_current < 5000:
            user.noor_current = 5000


def _test_level_reply(level: int) -> str:
    if level == 1:
        return "✅ برای تست، وارد سطح ۱ شدی. پیشرفت سطح: ۱/۱۲\nقابلیت‌های سطح ۱ دوباره قفل شدند."
    if level == 2:
        return "✅ برای تست، وارد سطح ۲ شدی. پیشرفت سطح: ۱/۲۴"
    return "✅ برای تست، وارد سطح ۳ شدی و نورت ۵۰۰۰ شد. بنویس: «شغل»"


async def _reset_everything(telegram_id: int, username: str | None, first_name: str | None) -> None:
    """پاک‌سازی کامل اطلاعات بازی یک کاربر (فقط برای تست)."""
    from sqlalchemy import delete, or_, select

    from bot.database.models import (
        BankPrompt,
        Chest,
        DhikrCircleMember,
        DhikrUnlock,
        DuaQueue,
        DuaQueueAnswer,
        DuaQueueExtraMessage,
        LoanRequest,
        MarketListing,
        MarketPricePrompt,
        User,
        UserProduct,
        UserProduction,
        UserRawMaterial,
    )

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(session, telegram_id, username, first_name)

            # ابتدا ارجاع کاربر به حلقه را بردار تا حذف ردیف‌ها به FK نخورد.
            user.active_circle_id = None
            await session.flush()

            # صف‌های دعای خود کاربر (همراه پاسخ‌ها و پیام‌های اضافه‌شان) + پاسخ‌هایی که او به دیگران داده.
            owned_queues = select(DuaQueue.id).where(DuaQueue.owner_user_id == user.id)
            await session.execute(
                delete(DuaQueueAnswer).where(
                    or_(
                        DuaQueueAnswer.queue_id.in_(owned_queues),
                        DuaQueueAnswer.responder_user_id == user.id,
                    )
                )
            )
            await session.execute(
                delete(DuaQueueExtraMessage).where(DuaQueueExtraMessage.queue_id.in_(owned_queues))
            )
            await session.execute(delete(DuaQueue).where(DuaQueue.owner_user_id == user.id))

            # عضویت در حلقه‌ها (خود حلقه‌ها برای بقیه‌ی اعضا باقی می‌مانند).
            await session.execute(
                delete(DhikrCircleMember).where(DhikrCircleMember.user_id == user.id)
            )

            for model in (
                DhikrUnlock,
                Chest,
                UserProduction,
                UserRawMaterial,
                UserProduct,
                MarketPricePrompt,
                BankPrompt,
            ):
                await session.execute(delete(model).where(model.user_id == user.id))
            await session.execute(delete(MarketListing).where(MarketListing.seller_id == user.id))
            await session.execute(
                delete(LoanRequest).where(
                    or_(LoanRequest.borrower_id == user.id, LoanRequest.lender_id == user.id)
                )
            )

            # همه‌ی ستون‌های خود کاربر به مقدار پیش‌فرض برمی‌گردند، جز هویت او.
            keep = {"id", "telegram_id", "username", "first_name", "created_at"}
            for column in User.__table__.columns:
                if column.key in keep:
                    continue
                default = column.default
                value = default.arg if default is not None and default.is_scalar else None
                setattr(user, column.key, value)
            await session.flush()


# ---------------------------------------------------------------------------
# هندلر اصلی پیام‌های متنی
# ---------------------------------------------------------------------------


@router.message()
async def handle_text_message(
    message: Message,
    bot: Bot,
    event_update: Update,
) -> None:
    if message.text is None:
        return

    if message.chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.PRIVATE,
    ):
        return

    if message.from_user is None or message.from_user.is_bot:
        return

    normalized = normalize_text(message.text)

    # -----------------------------------------------------------------------
    # تست سریع سطح‌ها: «سطح 1» / «سطح 2» / «سطح 3» (موقت؛ قبل از انتشار نهایی حذف شود)
    # اعداد فارسی/عربی هم پذیرفته می‌شوند («سطح ۲»).
    # -----------------------------------------------------------------------
    test_level = _parse_test_level_command(normalized)
    if test_level is not None:
        async with async_session_factory() as session:
            async with session.begin():
                user = await get_or_create_user(
                    session,
                    message.from_user.id,
                    message.from_user.username,
                    message.from_user.first_name,
                )
                _apply_test_level(user, test_level)
                await session.flush()
        await message.reply(_test_level_reply(test_level))
        return

    # -----------------------------------------------------------------------
    # تست: ریست شغل (موقت؛ قبل از انتشار نهایی حذف شود)
    # شغل، ابزار، تومان، مواد اولیه، تولید در جریان و انبار محصولات را پاک می‌کند تا
    # بشود دوباره شغل انتخاب کرد. نور و سطح دست‌نخورده می‌مانند.
    # -----------------------------------------------------------------------
    if normalized == "ریست شغل":
        from sqlalchemy import delete

        from bot.database.models import (
            MarketListing,
            MarketPricePrompt,
            UserProduct,
            UserProduction,
            UserRawMaterial,
        )

        async with async_session_factory() as session:
            async with session.begin():
                user = await get_or_create_user(
                    session,
                    message.from_user.id,
                    message.from_user.username,
                    message.from_user.first_name,
                )
                for model in (UserProduction, UserRawMaterial, UserProduct, MarketPricePrompt):
                    await session.execute(delete(model).where(model.user_id == user.id))
                await session.execute(delete(MarketListing).where(MarketListing.seller_id == user.id))
                user.job_key = None
                user.job_selected_at = None
                user.tool_level = 0
                user.toman = 0
                await session.flush()
        await message.reply("♻️ شغلت ریست شد. بنویس: «شغل» و دوباره انتخاب کن.")
        return

    # -----------------------------------------------------------------------
    # تست: ریست همه (موقت؛ قبل از انتشار نهایی حذف شود)
    # همه‌ی اطلاعات بازی کاربر را صفر می‌کند (نور، تومان، سطح، شغل، ذکرها، صندوقچه‌ها،
    # صف دعا، حلقه، انبار، مارکت، بانک و ...) تا مثل کاربر کاملاً تازه شود.
    # فقط هویت تلگرامی (telegram_id / username / نام / تاریخ ساخت) می‌ماند.
    # -----------------------------------------------------------------------
    if normalized == "ریست همه":
        await _reset_everything(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        await message.reply(
            "♻️ همه‌چیز صفر شد؛ نور، پول، سطح، شغل و بقیه‌ی اطلاعاتت پاک شد.\n"
            "برای شروع دوباره، اولین صلوات رو بفرست."
        )
        return

    # -----------------------------------------------------------------------
    # دعوت مستقیم به حلقه
    # -----------------------------------------------------------------------
    # سه حالت مجاز:
    #   ۱) ریپلای روی پیام شخص و نوشتن «حلقه ذکر»
    #   ۲) «حلقه ذکر @username»
    #   ۳) «حلقه ذکر <telegram_id>»
    # در هر سه حالت، عضویت فقط بعد از تأیید خصوصیِ هدف انجام می‌شود.
    if (
        message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
        and (normalized == COMMAND_DHIKR_CIRCLE or normalized.startswith(COMMAND_DHIKR_CIRCLE + " "))
    ):
        from bot.handlers.dhikr_circle import invite_user_from_message

        handled = await invite_user_from_message(message, bot)
        if handled:
            return

    # -----------------------------------------------------------------------
    # دستورات ثابت بازی
    # -----------------------------------------------------------------------
    #
    # این دستورات فعالیت صلوات/ذکر محسوب نمی‌شوند و در PV هم مجاز هستند.
    # -----------------------------------------------------------------------

    if normalized == COMMAND_BANK_AZKAR:
        from bot.handlers.commands import show_bank_azkar

        await show_bank_azkar(message)
        return

    if normalized == COMMAND_NAMEH_AMAL:
        from bot.handlers.commands import show_nameh_amal

        await show_nameh_amal(message)
        return

    if normalized == COMMAND_TASBIH:
        from bot.handlers.commands import show_tasbih

        await show_tasbih(message)
        return

    # Level 3: مشاغل و مارکت (پنل شخصی؛ در گروه و PV مجاز)
    if normalized in (COMMAND_JOB, COMMAND_JOB_ALIAS):
        from bot.handlers.job_panel import show_job_panel

        await show_job_panel(message)
        return

    if normalized == COMMAND_WAREHOUSE:
        from bot.handlers.job_panel import show_warehouse_panel

        await show_warehouse_panel(message)
        return

    if normalized in (COMMAND_STORE, COMMAND_MARKET):
        from bot.handlers.store_panel import show_store_panel

        await show_store_panel(message)
        return

    if normalized == COMMAND_BANK:
        from bot.handlers.bank_panel import show_bank_panel

        await show_bank_panel(message)
        return

    if normalized == COMMAND_DUA_QUEUE:
        from bot.handlers.dua_queue import create_dua_queue_command

        await create_dua_queue_command(message)
        return

    if normalized == COMMAND_DHIKR_CIRCLE:
        from bot.handlers.dhikr_circle import create_dhikr_circle_command

        await create_dhikr_circle_command(message)
        return

    # -----------------------------------------------------------------------
    # Level 2: پاسخ به پنل «التماس دعا» (ریپلای روی پیام پنل با متن ذکر آن)
    # -----------------------------------------------------------------------

    # Level 3: ورود قیمت آگهی فروشگاه (ریپلای روی پیام پنل؛ در گروه و PV)
    if message.reply_to_message is not None:
        from bot.handlers.store_panel import try_handle_price_reply

        if await try_handle_price_reply(message, event_update):
            return

    # Level 3: ورود متن بانک — کارت‌به‌کارت / مبلغ وام (ریپلای روی پیام پنل؛ در گروه و PV)
    if message.reply_to_message is not None:
        from bot.handlers.bank_panel import try_handle_bank_reply

        if await try_handle_bank_reply(message, event_update):
            return

    if message.reply_to_message is not None and _chat_allows_activity(message.chat.type):
        from bot.handlers.dua_queue import try_handle_dua_queue_reply

        if await try_handle_dua_queue_reply(message, bot, event_update):
            return

    # -----------------------------------------------------------------------
    # فعالیت صلوات/ذکر فقط در گروه
    # -----------------------------------------------------------------------

    if not _chat_allows_activity(message.chat.type):
        return

    async with async_session_factory() as session:
        async with session.begin():
            outcome = await process_activity(
                session,
                update_id=event_update.update_id,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                chat_id=message.chat.id,
                raw_text=message.text,
            )

    await _render_outcome(
        bot,
        message,
        outcome,
    )


# ---------------------------------------------------------------------------
# نمایش نتیجه فعالیت
# ---------------------------------------------------------------------------


async def _render_outcome(
    bot: Bot,
    message: Message,
    outcome: ActivityOutcome,
) -> None:
    status = outcome.status

    # -----------------------------------------------------------------------
    # وضعیت‌هایی که هیچ پیامی نباید داشته باشند
    # -----------------------------------------------------------------------

    if status in (
        OutcomeStatus.DUPLICATE_UPDATE,
        OutcomeStatus.UNRELATED,
        OutcomeStatus.INVALID_SILENT,
        OutcomeStatus.CIRCLE_DAILY_LIMIT,
    ):
        return

    # -----------------------------------------------------------------------
    # Level 3: کاربر به‌خاطر ندادن بدهی در زندان است
    # -----------------------------------------------------------------------

    if status == OutcomeStatus.JAILED:
        from bot.texts import bank_texts as bank_texts_mod

        await message.reply(bank_texts_mod.jailed_message(outcome.jail_remaining_seconds))
        return

    # -----------------------------------------------------------------------
    # ذکر قفل‌شده
    # -----------------------------------------------------------------------

    if status == OutcomeStatus.LOCKED_DHIKR:
        dhikr = outcome.dhikr_def

        await message.reply(
            (
                f"🔒 «{dhikr.display_name}» هنوز باز نشده. "
                f"برای باز کردنش «{COMMAND_BANK_AZKAR}» رو بفرست."
            ),
            reply_markup=dhikr_unlock_button(dhikr),
        )
        return

    # -----------------------------------------------------------------------
    # Cooldown
    # -----------------------------------------------------------------------

    if status == OutcomeStatus.COOLDOWN:
        remaining = outcome.cooldown_remaining_seconds or 0

        if outcome.activity_kind == ActivityKind.SALAWAT:
            cooldown_text = texts.salawat_cooldown_message(
                remaining
            )
        else:
            cooldown_text = texts.dhikr_cooldown_message(
                remaining
            )

        sent = await message.reply(cooldown_text)

        # پیام cooldown بعد از ۱۰ ثانیه حذف می‌شود.
        _schedule_autodelete(
            bot,
            sent,
        )

        return

    # -----------------------------------------------------------------------
    # فعالیت موفق
    # -----------------------------------------------------------------------

    if status == OutcomeStatus.SUCCESS:
        await _render_success(
            bot,
            message,
            outcome,
        )
        return


async def _send_circle_pv_result(
    bot: Bot,
    message: Message,
    outcome: ActivityOutcome,
) -> None:
    """نتیجه‌ی کامل و اختصاصی ذکر حلقه در PV کاربر."""
    progress = f"{outcome.circle_daily_count} از {outcome.circle_daily_target}"
    text = (
        "🧿 **ذکر حلقه ثبت شد**\n\n"
        f"✨ +{outcome.noor_reward} نورِ حلقه\n"
        f"🌿 سهم امروزت در حلقه: **{progress}**\n"
        f"💫 نور معنویتت: {outcome.noor_current}"
    )
    try:
        await bot.send_message(chat_id=message.from_user.id, text=text, parse_mode="Markdown")
    except Exception:
        logger.warning("ارسال نتیجه ذکر حلقه به PV کاربر %s ناموفق بود", message.from_user.id)


# ---------------------------------------------------------------------------
# نمایش موفقیت فعالیت
# ---------------------------------------------------------------------------


async def _render_success(
    bot: Bot,
    message: Message,
    outcome: ActivityOutcome,
) -> None:

    # -----------------------------------------------------------------------
    # ذکر حلقه — پیام اختصاصی و بدون قالب ذکرهای عادی/بانک اذکار
    # -----------------------------------------------------------------------

    if outcome.is_circle_dhikr:
        progress = f"{outcome.circle_daily_count} از {outcome.circle_daily_target}"

        if outcome.use_full_message:
            await message.reply(
                f"🧿 **ذکر حلقه ثبت شد**\n\n"
                f"✨ +{outcome.noor_reward} نورِ حلقه\n"
                f"🌿 سهم امروزت در حلقه: **{progress}**\n"
                f"💫 نور معنویتت: {outcome.noor_current}",
                parse_mode="Markdown",
            )
        else:
            # ۷۰٪: فقط reaction در گروه + همین نتیجه‌ی کامل در PV
            reacted = await _try_react(bot, message)
            if reacted:
                await _send_circle_pv_result(bot, message, outcome)
            else:
                # اگر Telegram reaction را نپذیرفت، نتیجه را از دست ندهیم.
                await message.reply(
                    f"🧿 **ذکر حلقه ثبت شد**\n\n"
                        f"✨ +{outcome.noor_reward} نورِ حلقه\n"
                    f"🌿 سهم امروزت در حلقه: **{progress}**\n"
                    f"💫 نور معنویتت: {outcome.noor_current}",
                    parse_mode="Markdown",
                )

        # پنل بازِ حلقه بلافاصله بعد از ثبت موفق، برای اعضای حاضر refresh می‌شود.
        try:
            from bot.handlers.dhikr_circle import refresh_circle_panels
            await refresh_circle_panels(bot, message.from_user.id)
        except Exception:
            logger.exception("بروزرسانی خودکار پنل حلقه ناموفق بود")

        if outcome.circle_just_completed_today:
            await message.reply(texts.CIRCLE_DAILY_TARGET_COMPLETE)
        if outcome.circle_milestone_winners:
            winner_labels = [
                f"@{username}" if username else (first_name or "کاربر")
                for _telegram_id, username, first_name in outcome.circle_milestone_winners
            ]
            await message.reply(
                texts.circle_milestone_announcement(
                    winner_labels,
                    reward_each=circle_domain.CIRCLE_MILESTONE_REWARD_PER_MEMBER,
                    total=circle_domain.CIRCLE_MILESTONE_TOTAL_NOOR,
                ),
                parse_mode="Markdown",
            )
        return

    # -----------------------------------------------------------------------
    # اولین فعالیت
    # -----------------------------------------------------------------------
    #
    # اولین صلوات همیشه پیام کامل معرفی بازی را در گروه می‌گیرد.
    # هیچ reaction یا PV برای آن ارسال نمی‌شود.
    # -----------------------------------------------------------------------

    if outcome.is_first_activity:
        await message.reply(
            texts.first_salawat_registered(
                outcome.noor_reward,
                outcome.noor_current,
                outcome.level_progress,
                outcome.level_progress_total,
            ),
            parse_mode="Markdown",
        )

    # -----------------------------------------------------------------------
    # Level 2: milestone باز شدن «التماس دعا» (ناشی از دهمین ذکر روزانه،
    # نه صلوات؛ به همین دلیل قبل از شاخه‌ی عمومی milestoneهای صلوات بررسی می‌شود).
    # -----------------------------------------------------------------------

    elif outcome.milestone_kind == "dua_queue_unlocked":
        await message.reply(
            texts.dua_queue_unlocked_message(
                outcome.noor_reward,
                outcome.noor_current,
            ),
            parse_mode="Markdown",
        )

    # -----------------------------------------------------------------------
    # Milestoneهای ۳ / ۶ / ۹ / ۱۲
    # -----------------------------------------------------------------------
    #
    # همه‌چیز در یک پیام:
    # صلوات + نور + نور معنویتت + نوار پیشرفت + قابلیت جدید
    # -----------------------------------------------------------------------

    elif outcome.milestone_kind == MILESTONE_LEVEL_UP_3:
        await message.reply(
            job_texts.level_up_3_message(
                outcome.noor_reward,
                outcome.noor_current,
                outcome.level_progress,
                outcome.level_progress_total,
            ),
            parse_mode="Markdown",
        )

    elif outcome.milestone_kind is not None:
        await message.reply(
            texts.salawat_milestone_message(
                milestone_kind=outcome.milestone_kind,
                noor_reward=outcome.noor_reward,
                noor_current=outcome.noor_current,
                level_progress=outcome.level_progress,
                level_total=outcome.level_progress_total,
            ),
            parse_mode="Markdown",
        )

    # -----------------------------------------------------------------------
    # ۳۳٪ پیام کامل در گروه
    # -----------------------------------------------------------------------
    #
    # اینجا نوار پیشرفت واقعی صلوات داخل _full_group_text ساخته می‌شود.
    # -----------------------------------------------------------------------

    elif outcome.use_full_message:
        await message.reply(
            _full_group_text(
                outcome,
                message.from_user.id,
            )
        )

    # -----------------------------------------------------------------------
    # ۶۷٪: Reaction + نتیجه
    # -----------------------------------------------------------------------

    else:
        reacted = await _try_react(
            bot,
            message,
        )

        # -------------------------------------------------------------------
        # اگر Reaction از نظر فنی ثبت نشد:
        # پیام کامل در گروه
        # بدون PV
        # -------------------------------------------------------------------

        if not reacted:
            await message.reply(
                _full_group_text(
                    outcome,
                    message.from_user.id,
                )
            )

        # -------------------------------------------------------------------
        # اولین بار که کاربر نتیجه را با Reaction می‌گیرد:
        # Reaction + توضیح در گروه
        #
        # خود این پیام نتیجه واقعی فعالیت است.
        # بنابراین PV ارسال نمی‌شود.
        # -------------------------------------------------------------------

        elif outcome.needs_reaction_explanation:

            progress_line = None

            if outcome.activity_kind == ActivityKind.SALAWAT:
                progress_line = render_progress_bar(
                    outcome.level_progress,
                    outcome.level_progress_total,
                )

            await message.reply(
                texts.reaction_first_time_explanation(
                    outcome.noor_reward,
                    outcome.noor_current,
                    progress_line,
                    "dhikr" if outcome.activity_kind == ActivityKind.DHIKR else "salawat",
                )
            )

        # -------------------------------------------------------------------
        # Reaction معمولی:
        # نتیجه فقط در PV
        # -------------------------------------------------------------------

        else:
            await _send_pv_result(
                bot,
                message,
                outcome,
            )

    # -----------------------------------------------------------------------
    # صندوقچه
    # -----------------------------------------------------------------------
    #
    # صندوقچه مستقل از نتیجه فعالیت است و همیشه در گروه نمایش داده می‌شود.
    # -----------------------------------------------------------------------

    if outcome.chest is not None:
        await _send_chest_message(
            bot,
            message,
            outcome,
        )

    # -----------------------------------------------------------------------
    # Level 2: حلقه ذکر — طبق طراحی «بدون فشار روانی/FOMO»، این پیام‌ها فقط در دو
    # لحظه‌ی معنادار نشان داده می‌شوند (نه روی هر ذکر عادی عضو حلقه):
    # ۱) وقتی خودِ کاربر همین الان به ۱۰/۱۰ امروزش رسیده.
    # ۲) وقتی همین فعالیت باعث تکمیل milestone پنج‌نفره شده (پاداش گروهی پرداخت شد).
    # -----------------------------------------------------------------------

    if outcome.circle_just_completed_today:
        await message.reply(texts.CIRCLE_DAILY_TARGET_COMPLETE)

    if outcome.circle_milestone_winners:
        winner_labels = [
            f"@{username}" if username else (first_name or "کاربر")
            for _telegram_id, username, first_name in outcome.circle_milestone_winners
        ]
        await message.reply(
            texts.circle_milestone_announcement(
                winner_labels,
                reward_each=circle_domain.CIRCLE_MILESTONE_REWARD_PER_MEMBER,
                total=circle_domain.CIRCLE_MILESTONE_TOTAL_NOOR,
            ),
            parse_mode="Markdown",
        )

    # -----------------------------------------------------------------------
    # Level 3: پیشرفت تولید شغل — طبق همان طراحی «بدون شلوغی»، پیشرفت میانی فقط در PV
    # فرستاده می‌شود و فقط لحظه‌ی تکمیل تولید (و محصولات به‌دست‌آمده) در گروه اعلام می‌شود.
    # -----------------------------------------------------------------------

    prod = outcome.production
    if prod is not None:
        product = jobs_domain.PRODUCT_BY_KEY.get(prod.product_key)
        if product is not None:
            if prod.completed:
                await message.reply(job_texts.production_complete_group(product, prod.produced))
            else:
                try:
                    await bot.send_message(
                        chat_id=message.from_user.id,
                        text=job_texts.production_progress_pv(product, prod.done, prod.required),
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("ارسال پیشرفت تولید به PV ناموفق بود", exc_info=True)


# ---------------------------------------------------------------------------
# حذف خودکار پیام cooldown
# ---------------------------------------------------------------------------


def _schedule_autodelete(
    bot: Bot,
    sent_message: Message,
    delay_seconds: float = 10.0,
) -> None:
    """
    حذف خودکار پیام cooldown بعد از ۱۰ ثانیه.

    هیچ پیام خودکار دیگری هنگام تمام‌شدن cooldown فرستاده نمی‌شود.
    فقط همین پیام حذف می‌شود.
    """

    async def _job() -> None:
        await asyncio.sleep(delay_seconds)

        try:
            await bot.delete_message(
                chat_id=sent_message.chat.id,
                message_id=sent_message.message_id,
            )
        except Exception:  # noqa: BLE001
            # مثلاً کاربر خودش پیام را حذف کرده یا زمان حذف گذشته است.
            logger.debug(
                "حذف خودکار پیام cooldown ناموفق بود",
                exc_info=True,
            )

    asyncio.create_task(_job())


# ---------------------------------------------------------------------------
# پیام کامل موفقیت عادی
# ---------------------------------------------------------------------------


def _full_group_text(
    outcome: ActivityOutcome,
    telegram_id: int,
) -> str:
    """
    پیام موفقیت عادی صلوات/ذکر.

    برای صلوات:
        نوار پیشرفت واقعی صلوات نیز به پیام اضافه می‌شود.

    برای ذکر:
        نوار پیشرفت صلوات نمایش داده نمی‌شود.

    طبق قابلیت «متن پایانی»، دقیقاً یک جمله‌ی تصادفی
    که در ۱۰ متن اخیر همین کاربر تکراری نباشد،
    به انتهای پیام اضافه می‌شود.
    """

    closing_line = closing_lines.pick_closing_line(
        telegram_id
    )

    # -----------------------------------------------------------------------
    # صلوات
    # -----------------------------------------------------------------------

    if outcome.activity_kind == ActivityKind.SALAWAT:

        # نوار پیشرفت واقعی صلوات
        #
        # مثال:
        # ▰▰▰▰▰▰▰▰▰▰▰▱ ۱۱ از ۱۲
        #
        # یا:
        # ▰▰▰▰▰▰▰▰▰▰▰▰ ۱۲ از ۱۲
        progress_line = render_progress_bar(
            outcome.level_progress,
            outcome.level_progress_total,
        )

        return texts.salawat_success(
            outcome.noor_reward,
            outcome.noor_current,
            outcome.next_cooldown_seconds,
            closing_line,
            progress_line,
        )

    # -----------------------------------------------------------------------
    # ذکر
    # -----------------------------------------------------------------------

    return texts.dhikr_success(
        outcome.noor_reward,
        outcome.noor_current,
        outcome.next_cooldown_seconds,
        closing_line,
    )


# ---------------------------------------------------------------------------
# Reaction
# ---------------------------------------------------------------------------


async def _try_react(
    bot: Bot,
    message: Message,
) -> bool:
    try:
        await bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[
                ReactionTypeEmoji(
                    emoji=texts.SUCCESS_REACTION_EMOJI
                )
            ],
        )

        return True

    except Exception:  # noqa: BLE001
        logger.exception(
            "ثبت reaction ناموفق بود"
        )
        return False


# ---------------------------------------------------------------------------
# ارسال نتیجه فعالیت به PV
# ---------------------------------------------------------------------------


async def _send_pv_result(
    bot: Bot,
    message: Message,
    outcome: ActivityOutcome,
) -> None:

    progress_line = None

    if outcome.activity_kind == ActivityKind.SALAWAT:
        progress_line = render_progress_bar(
            outcome.level_progress,
            outcome.level_progress_total,
        )

    if outcome.activity_kind == ActivityKind.DHIKR:
        activity_kind = "dhikr"
    else:
        activity_kind = "salawat"

    text = texts.pv_activity_result(
        outcome.noor_reward,
        outcome.noor_current,
        progress_line,
        activity_kind,
    )

    try:
        await bot.send_message(
            chat_id=message.from_user.id,
            text=text,
            parse_mode="Markdown",
        )

    except Exception:  # noqa: BLE001
        logger.warning(
            "ارسال نتیجه فعالیت به PV کاربر %s ناموفق بود",
            message.from_user.id,
        )


# ---------------------------------------------------------------------------
# صندوقچه
# ---------------------------------------------------------------------------


async def _send_chest_message(
    bot: Bot,
    message: Message,
    outcome: ActivityOutcome,
) -> None:

    text = (
        texts.CHEST_FIRST_TIME_MESSAGE
        if outcome.chest_is_first_ever
        else texts.CHEST_SUBSEQUENT_MESSAGE
    )

    sent = await message.reply(
        text,
        reply_markup=chest_open_button(
            outcome.chest.id
        ),
        parse_mode="Markdown",
    )

    # -----------------------------------------------------------------------
    # ذخیره message_id صندوقچه
    # -----------------------------------------------------------------------

    async with async_session_factory() as session:
        async with session.begin():
            from sqlalchemy import update

            from bot.database.models import Chest as ChestModel

            await session.execute(
                update(ChestModel)
                .where(
                    ChestModel.id == outcome.chest.id
                )
                .values(
                    message_id=sent.message_id
                )
            )
