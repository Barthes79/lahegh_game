"""
تسک‌های پس‌زمینه‌ی پروژه.

۱) یادآوری غیرفعالی (بخش ۱۷ سند اصلی).
۲) Level 2 — بستن خودکار صف‌های دعای منقضی (۱۲ ساعت)، حتی بدون اینکه کسی روی دکمه
   کلیک کند. این Job در همین حلقه‌ی زمان‌بندی موجود اجرا می‌شود (scheduler جدید ساخته نشده)
   و idempotent است: فقط صف‌های closed=False بررسی می‌شوند.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup

from bot.config import settings
from bot.database.engine import async_session_factory
from bot.domain import dua_queue as dua_queue_domain
from bot.services.dua_queue_service import close_expired_queues, get_panel_view
from bot.handlers.dhikr_circle import expire_circle_panels
from bot.services.reminder_service import build_user_mention, get_users_due_for_reminder, mark_reminded
from bot.texts import messages as texts

logger = logging.getLogger(__name__)

_EMPTY_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[])


async def _send_reminders_once(bot: Bot) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            due_users = await get_users_due_for_reminder(session)
            for user in due_users:
                mention = build_user_mention(user)
                # متن یادآوری طبق بخش ۱۷ سند:
                text = (
                    f"🌙 {mention}\n\n"
                    "گاهی فقط یک صلوات، یک ذکر کوتاه، می‌تونه حال آدم رو عوض کنه...\n\n"
                    "🤲 اگر دلت خواست، چند لحظه با صلوات و ذکر، دوباره راهت رو ادامه بده.\n\n"
                    "✨ شاید قدم بعدی تو، همین الان باشه."
                )
                try:
                    await bot.send_message(chat_id=user.active_chat_id, text=text, parse_mode=ParseMode.HTML)
                    mark_reminded(user)
                except Exception:  # noqa: BLE001
                    logger.exception("ارسال یادآوری به کاربر %s ناموفق بود", user.telegram_id)


async def _close_expired_dua_queues_once(bot: Bot) -> None:
    """Level 2: پنل‌های التماس دعایی که ۱۲ ساعت از آن‌ها گذشته را می‌بندد و پنلشان را edit می‌کند."""
    to_edit: list[tuple[int, int, str]] = []
    async with async_session_factory() as session:
        async with session.begin():
            closed_queues = await close_expired_queues(session)
            # متن نهایی (شامل اسم دعاکننده‌ها و نور صاحب پنل) همین‌جا داخل session ساخته می‌شود.
            for q in closed_queues:
                if q.message_id is None:
                    continue
                view = await get_panel_view(session, q)
                text = texts.dua_queue_panel_text(
                    q.answers_count,
                    dua_queue_domain.QUEUE_MAX_ANSWERS,
                    owner_name=view.owner_name,
                    owner_telegram_id=view.owner_telegram_id,
                    responders=view.responders,
                    owner_earned=view.owner_earned,
                    closed=True,
                )
                to_edit.append((q.chat_id, q.message_id, text))

    for chat_id, message_id, text in to_edit:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                # پنل‌های قدیمی هنوز دکمه دارند؛ با این edit دکمه‌شان هم حذف می‌شود.
                reply_markup=_EMPTY_KEYBOARD,
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001
            # مثلاً پیام قبلاً حذف شده یا متن تغییری نکرده — بی‌اهمیت است.
            logger.debug("edit پنل صف دعای منقضی‌شده ناموفق بود (chat=%s, message=%s)", chat_id, message_id)


async def reminder_loop(bot: Bot) -> None:
    interval = settings.reminder_check_interval_minutes * 60
    while True:
        try:
            await _send_reminders_once(bot)
        except Exception:  # noqa: BLE001
            logger.exception("خطا در حلقه‌ی یادآوری")
        try:
            await _close_expired_dua_queues_once(bot)
            await expire_circle_panels(bot)
        except Exception:  # noqa: BLE001
            logger.exception("خطا در بستن خودکار صف‌های دعای منقضی")
        await asyncio.sleep(interval)
