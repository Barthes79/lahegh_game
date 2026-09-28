"""
هندلرهای دکمه‌های inline: unlock ذکر، باز کردن صندوقچه.

(ارتقای تسبیح دیگر اینجا نیست؛ پنل تسبیح یک ماژول owner-scoped مستقل است، مثل پنل بانک
اذکار — به bot/handlers/tasbih_panel.py نگاه کن.)

هر callback ابتدا با update_id واقعی تلگرام «claim» می‌شود (بخش ۲۰: جلوگیری از double click)؛
اگر قبلاً پردازش شده، فقط callback بی‌صدا answer می‌شود و کاری انجام نمی‌شود.
"""
from __future__ import annotations

import random

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Update

_EMPTY_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[])

from bot.database.engine import async_session_factory
from bot.database.models import Chest, User
from bot.domain.dhikr_data import DHIKR_BY_KEY
from bot.keyboards.inline import confirm_cancel_keyboard, dhikr_unlock_button
from bot.services.chest_service import ChestOpenResult, open_chest
from bot.services.idempotency import try_claim_update
from bot.services.unlock_service import UnlockResult, unlock_dhikr
from bot.services.user_service import get_or_create_user
from bot.texts import messages as texts

router = Router(name="callbacks")


@router.callback_query(lambda c: c.data and c.data.startswith("dhikr_unlock_ask:"))
async def on_dhikr_unlock_ask(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    dhikr = DHIKR_BY_KEY.get(key)
    if dhikr is None:
        await callback.answer()
        return
    await callback.message.answer(
        texts.unlock_confirm_prompt(dhikr),
        reply_markup=confirm_cancel_keyboard(
            confirm_data=f"dhikr_unlock_confirm:{key}", cancel_data="dhikr_unlock_cancel"
        ),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "dhikr_unlock_cancel")
async def on_dhikr_unlock_cancel(callback: CallbackQuery) -> None:
    await callback.answer("لغو شد")
    if callback.message:
        await callback.message.delete()


@router.callback_query(lambda c: c.data and c.data.startswith("dhikr_unlock_confirm:"))
async def on_dhikr_unlock_confirm(callback: CallbackQuery, event_update: Update) -> None:
    key = callback.data.split(":", 1)[1]
    dhikr = DHIKR_BY_KEY.get(key)
    if dhikr is None or callback.from_user is None:
        await callback.answer()
        return

    async with async_session_factory() as session:
        async with session.begin():
            claimed = await try_claim_update(session, event_update.update_id)
            if not claimed:
                await callback.answer()
                return

            user = await get_or_create_user(
                session, callback.from_user.id, callback.from_user.username, callback.from_user.first_name
            )
            outcome = await unlock_dhikr(session, user, dhikr)

    if outcome.result == UnlockResult.SUCCESS:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(texts.unlock_success(dhikr), reply_markup=_EMPTY_KEYBOARD)
    elif outcome.result == UnlockResult.ALREADY_UNLOCKED:
        await callback.answer(texts.UNLOCK_ALREADY_DONE)
        if callback.message:
            await callback.message.delete()
    else:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                texts.unlock_insufficient_noor(dhikr, outcome.noor_current)
            )


@router.callback_query(lambda c: c.data and c.data.startswith("chest_open:"))
async def on_chest_open(callback: CallbackQuery, event_update: Update) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    chest_id = int(callback.data.split(":", 1)[1])

    async with async_session_factory() as session:
        async with session.begin():
            claimed = await try_claim_update(session, event_update.update_id)
            if not claimed:
                await callback.answer()
                return

            chest = await session.get(Chest, chest_id)
            if chest is None:
                await callback.answer()
                return
            user = await session.get(User, chest.user_id)
            outcome = open_chest(chest, user, callback.from_user.id)

    if outcome.result == ChestOpenResult.SUCCESS:
        await callback.answer()
        if callback.message:
            motivational_line = random.choice(texts.CHEST_MOTIVATIONAL_LINES)
            await callback.message.edit_text(
                texts.chest_opened_message(outcome.reward_noor, outcome.noor_current, motivational_line),
                reply_markup=_EMPTY_KEYBOARD,
                parse_mode="Markdown",
            )
    elif outcome.result == ChestOpenResult.NOT_OWNER:
        await callback.answer(texts.CHEST_NOT_OWNER, show_alert=True)
    elif outcome.result == ChestOpenResult.ALREADY_OPENED:
        await callback.answer(texts.CHEST_ALREADY_OPENED)
    elif outcome.result == ChestOpenResult.EXPIRED:
        await callback.answer(texts.CHEST_EXPIRED, show_alert=True)
        if callback.message:
            await callback.message.edit_text(texts.CHEST_EXPIRED)
