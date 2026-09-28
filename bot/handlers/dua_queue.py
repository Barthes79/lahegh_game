"""
هندلر «التماس دعا» (Level 2، ویژگی اول؛ نام داخلی: dua_queue).

- دستور «التماس دعا» (فقط در گروه؛ در PV بی‌سروصدا نادیده گرفته می‌شود) یک پنل جدید می‌سازد که
  یک ذکر تصادفی (قابل کپی) نمایش می‌دهد.
- بقیه‌ی کاربران با کپی کردن همان ذکر و ریپلای زدن روی خودِ پیام پنل پاسخ می‌دهند
  (try_handle_dua_queue_reply؛ از group_messages.handle_text_message صدا زده می‌شود). ثبت ذکرِ
  پاسخ‌دهنده دقیقاً از مسیر اصلی activity_service (از طریق dua_queue_service.answer_dua_queue) است.
- پنجمین پاسخ پنل را می‌بندد و به صاحب پنل بونوس می‌دهد.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, Update

from bot.database.engine import async_session_factory
from bot.database.models import DuaQueue
from bot.domain import dua_queue as dua_queue_domain
from bot.domain.dhikr_data import DUA_QUEUE_NORMALIZED_TEXTS
from bot.domain.normalization import normalize_text
from bot.services.activity_service import OutcomeStatus
from bot.services.dua_queue_service import (
    AnswerQueueResult,
    CreateQueueResult,
    answer_dua_queue,
    create_dua_queue,
    find_queue_by_panel_message,
    get_panel_view,
    get_queue_dhikr,
)
from bot.services.user_service import get_or_create_user
from bot.texts import messages as texts

logger = logging.getLogger(__name__)

router = Router(name="dua_queue")


# ---------------------------------------------------------------------------
# دستور «التماس دعا»
# ---------------------------------------------------------------------------


async def create_dua_queue_command(message: Message) -> None:
    # طبق تصمیم طراح: این قابلیت مفهوماً فقط در گروه معنا دارد (وابسته به chat_id همان گروه
    # است)؛ در PV مثل هر دستور بی‌ربط دیگر بی‌سروصدا نادیده گرفته می‌شود.
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if message.from_user is None:
        return

    owner_telegram_id = message.from_user.id
    chat_id = message.chat.id

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(
                session, owner_telegram_id, message.from_user.username, message.from_user.first_name
            )
            outcome = await create_dua_queue(session, user, chat_id)

    if outcome.result == CreateQueueResult.NOT_STARTED:
        # بازی هنوز شروع نشده -> بی‌سروصدا نادیده بگیر (مثل بقیه‌ی قابلیت‌های قفل).
        return

    if outcome.result == CreateQueueResult.QUOTA_NOT_COMPLETE:
        await message.reply(
            texts.dua_queue_quota_not_complete(
                outcome.daily_free_dhikr_count, dua_queue_domain.DAILY_FREE_DHIKR_REQUIRED
            )
        )
        return

    if outcome.result == CreateQueueResult.OWNER_COOLDOWN:
        await message.reply(texts.DUA_QUEUE_OWNER_COOLDOWN)
        return

    # --- SUCCESS ---
    queue = outcome.queue
    dhikr = outcome.dhikr

    sent = await message.reply(
        texts.dua_queue_panel_text(
            queue.answers_count,
            dua_queue_domain.QUEUE_MAX_ANSWERS,
            dhikr_text=dhikr.canonical_texts[0],
            owner_name=message.from_user.first_name,
            owner_telegram_id=owner_telegram_id,
        ),
        parse_mode="HTML",
    )

    async with async_session_factory() as session:
        async with session.begin():
            from sqlalchemy import update

            await session.execute(
                update(DuaQueue).where(DuaQueue.id == queue.id).values(message_id=sent.message_id)
            )


# ---------------------------------------------------------------------------
# پاسخ به پنل: ریپلای روی پیام پنل با متن ذکر
# ---------------------------------------------------------------------------


async def try_handle_dua_queue_reply(message: Message, bot: Bot, event_update: Update) -> bool:
    """
    اگر پیام یک ریپلای روی پنل «التماس دعا» با متنِ یکی از ذکرهای این قابلیت باشد، آن را
    پردازش می‌کند و True برمی‌گرداند (یعنی پیام مصرف شد و نباید به مسیر عادی ذکر برود).
    در غیر این صورت False برمی‌گرداند و پیام مثل همیشه ادامه می‌دهد.
    """
    reply = message.reply_to_message
    if reply is None or message.text is None or message.from_user is None:
        return False
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False

    # فیلتر سبک: بدون کوئری دیتابیس، فقط ریپلای‌هایی که متنشان یکی از ۵ ذکر است.
    if normalize_text(message.text) not in DUA_QUEUE_NORMALIZED_TEXTS:
        return False

    async with async_session_factory() as session:
        async with session.begin():
            queue = await find_queue_by_panel_message(session, message.chat.id, reply.message_id)
            if queue is None:
                return False
            outcome = await answer_dua_queue(
                session,
                queue=queue,
                update_id=event_update.update_id,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                raw_text=message.text,
            )

    result = outcome.result

    if result in (AnswerQueueResult.NOT_FOUND, AnswerQueueResult.TEXT_MISMATCH):
        # پنل قدیمی یا ذکر اشتباه (مثلاً ذکر پنل دیگری) -> بی‌سروصدا نادیده بگیر.
        return True

    if result in (
        AnswerQueueResult.OWNER_CANNOT_ANSWER,
        AnswerQueueResult.NOT_STARTED,
        AnswerQueueResult.ALREADY_ANSWERED,
        AnswerQueueResult.CLOSED,
    ):
        info_text = {
            AnswerQueueResult.OWNER_CANNOT_ANSWER: texts.DUA_QUEUE_OWNER_CANNOT_ANSWER,
            AnswerQueueResult.NOT_STARTED: texts.DUA_QUEUE_RESPONDER_NOT_STARTED,
            AnswerQueueResult.ALREADY_ANSWERED: texts.DUA_QUEUE_ALREADY_ANSWERED,
            AnswerQueueResult.CLOSED: texts.DUA_QUEUE_CLOSED,
        }[result]
        await _reply_temporary(bot, message, info_text)
        if result == AnswerQueueResult.CLOSED:
            await _refresh_panel(bot, outcome.queue)
        return True

    if result == AnswerQueueResult.DHIKR_FAILED:
        activity_outcome = outcome.activity_outcome
        status = activity_outcome.status if activity_outcome else None
        if status == OutcomeStatus.COOLDOWN:
            remaining = activity_outcome.cooldown_remaining_seconds or 0
            await _reply_temporary(bot, message, texts.dhikr_cooldown_message(remaining))
        elif status in (OutcomeStatus.DUPLICATE_UPDATE, OutcomeStatus.UNRELATED, OutcomeStatus.INVALID_SILENT):
            # retry/تکراری یا بازی شروع نشده -> بی‌سروصدا نادیده بگیر (بخش ۲۰).
            pass
        else:
            await _reply_temporary(bot, message, texts.DUA_QUEUE_ANSWER_FAILED)
        return True

    # --- SUCCESS ---
    activity_outcome = outcome.activity_outcome
    await message.reply(
        texts.dua_queue_answer_success(activity_outcome.noor_reward, activity_outcome.noor_current)
    )

    if activity_outcome.milestone_kind == "dua_queue_unlocked":
        # ممکن است همین پاسخ، دهمین ذکر امروزِ پاسخ‌دهنده هم باشد.
        await message.reply(
            texts.dua_queue_unlocked_message(activity_outcome.noor_reward, activity_outcome.noor_current),
            parse_mode="Markdown",
        )

    await _refresh_panel(bot, outcome.queue)

    if outcome.completion_bonus_paid:
        await message.reply(
            texts.dua_queue_completed_message(
                outcome.owner_first_name,
                outcome.owner_telegram_id,
                dua_queue_domain.QUEUE_OWNER_COMPLETION_BONUS,
            ),
            parse_mode="HTML",
        )

    return True


async def _reply_temporary(bot: Bot, message: Message, text: str) -> None:
    """پاسخ کوتاه اطلاع‌رسانی که بعد از ۱۰ ثانیه حذف می‌شود (مثل پیام cooldown)."""
    from bot.handlers.group_messages import _schedule_autodelete

    sent = await message.reply(text)
    _schedule_autodelete(bot, sent)


async def _refresh_panel(bot: Bot, queue: DuaQueue | None) -> None:
    """
    پنل را با اطلاعات به‌روز edit می‌کند: تعداد پاسخ، اسم دعاکننده‌ها و نور دریافتی صاحب پنل.
    اگر بسته شده باشد، متن «بسته شد» (همراه همین اطلاعات) نمایش داده می‌شود.
    """
    if queue is None or queue.message_id is None:
        return
    try:
        async with async_session_factory() as session:
            fresh = await session.get(DuaQueue, queue.id)
            if fresh is None:
                return
            view = await get_panel_view(session, fresh)
        dhikr = get_queue_dhikr(fresh)
        text = texts.dua_queue_panel_text(
            fresh.answers_count,
            dua_queue_domain.QUEUE_MAX_ANSWERS,
            dhikr_text=dhikr.canonical_texts[0] if dhikr else None,
            owner_name=view.owner_name,
            owner_telegram_id=view.owner_telegram_id,
            responders=view.responders,
            owner_earned=view.owner_earned,
            closed=fresh.closed,
        )
        await bot.edit_message_text(
            chat_id=fresh.chat_id,
            message_id=fresh.message_id,
            text=text,
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        # مثلاً متن تغییر نکرده یا پیام حذف شده — بی‌اهمیت است.
        logger.debug("بروزرسانی پنل التماس دعا ناموفق بود", exc_info=True)


# ---------------------------------------------------------------------------
# دکمه‌ی قدیمی «🤲 التماس دعا» (پنل‌های ساخته‌شده قبل از مکانیزم ریپلای)
# ---------------------------------------------------------------------------


@router.callback_query(lambda c: c.data and c.data.startswith("dua_ans:"))
async def on_legacy_dua_queue_button(callback: CallbackQuery) -> None:
    await callback.answer(texts.DUA_QUEUE_LEGACY_BUTTON, show_alert=True)
