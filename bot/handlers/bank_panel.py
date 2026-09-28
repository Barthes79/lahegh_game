"""
هندلر callbackهای پنل «بانک اذکار» (اصلاحات نهایی).

هر پنل یک پیام مستقل است که owner_id (شناسه‌ی تلگرام کاربری که آن را باز کرده) در
callback_data تمام دکمه‌هایش کدگذاری شده. این باعث می‌شود:
- هر بار کاربر «بانک اذکار» را بفرستد، یک پنل کاملاً جدید و مستقل ساخته شود.
- پنل‌های قبلی (برای همان یا کاربران دیگر) دست‌نخورده باقی بمانند.
- فقط صاحب پنل بتواند با دکمه‌های آن پنل کار کند؛ کلیک هر کاربر دیگری کاملاً بی‌پاسخ
  می‌ماند (حتی answer هم فراخوانی نمی‌شود).

تمام navigation (صفحه‌ی اصلی <-> جزئیات) و تمام مراحل خرید (تأیید/لغو/موفقیت/خطا) با
ویرایش همان یک پیام انجام می‌شود؛ هیچ‌وقت پیام جدیدی ساخته نمی‌شود.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Update

from bot.database.engine import async_session_factory
from bot.domain.dhikr_data import DHIKR_BY_KEY, DHIKR_LIST
from bot.keyboards.inline import (
    bank_azkar_back_keyboard,
    bank_azkar_detail_keyboard,
    bank_azkar_main_keyboard,
)
from bot.services.idempotency import try_claim_update
from bot.services.unlock_service import UnlockResult, is_unlocked, unlock_dhikr
from bot.services.user_service import get_or_create_user
from bot.texts import messages as texts

router = Router(name="bank_panel")


def _parse(data: str) -> tuple[str, int, str | None]:
    parts = data.split(":")
    action = parts[1]
    owner_id = int(parts[2])
    key = parts[3] if len(parts) > 3 else None
    return action, owner_id, key


@router.callback_query(lambda c: c.data and c.data.startswith("bnk:"))
async def on_bank_panel_callback(callback: CallbackQuery, event_update: Update) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return

    action, owner_id, key = _parse(callback.data)

    # فقط صاحب پنل — کلیک بقیه کاملاً بدون پاسخ (نه answer، نه edit)
    if callback.from_user.id != owner_id:
        return

    if action == "main":
        async with async_session_factory() as session:
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )
            unlocked_map = {d.key: await is_unlocked(session, user, d) for d in DHIKR_LIST}
        await callback.message.edit_caption(
            caption=texts.bank_azkar_panel_header(),
            reply_markup=bank_azkar_main_keyboard(owner_id, DHIKR_LIST, unlocked_map),
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    dhikr = DHIKR_BY_KEY.get(key) if key else None
    if dhikr is None:
        await callback.answer()
        return

    if action == "view":
        async with async_session_factory() as session:
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )
            unlocked = await is_unlocked(session, user, dhikr)
        text = texts.bank_azkar_detail_unlocked(dhikr) if unlocked else texts.bank_azkar_detail_locked(dhikr)
        await callback.message.edit_caption(
            caption=text,
            reply_markup=bank_azkar_detail_keyboard(owner_id, dhikr.key, unlocked),
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    if action == "buy":
        async with async_session_factory() as session:
            async with session.begin():
                claimed = await try_claim_update(session, event_update.update_id)
                if not claimed:
                    await callback.answer()
                    return
                user = await get_or_create_user(
                    session, owner_id, callback.from_user.username, callback.from_user.first_name
                )
                outcome = await unlock_dhikr(session, user, dhikr)

        await callback.answer()
        if outcome.result == UnlockResult.SUCCESS:
            await callback.message.edit_caption(
                caption=texts.bank_azkar_purchase_success(dhikr),
                reply_markup=bank_azkar_back_keyboard(owner_id),
                parse_mode="Markdown",
            )
        elif outcome.result == UnlockResult.ALREADY_UNLOCKED:
            await callback.message.edit_caption(
                caption=texts.bank_azkar_detail_unlocked(dhikr),
                reply_markup=bank_azkar_detail_keyboard(owner_id, dhikr.key, True),
                parse_mode="Markdown",
            )
        else:
            await callback.message.edit_caption(
                caption=texts.bank_azkar_purchase_insufficient(dhikr, outcome.noor_current),
                reply_markup=bank_azkar_back_keyboard(owner_id),
                parse_mode="Markdown",
            )
        return

    await callback.answer()
