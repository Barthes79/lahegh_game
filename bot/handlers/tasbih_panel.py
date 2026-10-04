"""
هندلر callbackهای پنل «تسبیح» (مثل پنل بانک اذکار: عکس + کپشن، owner-scoped).

هر پنل یک پیام مستقل (با عکس تسبیح) است که owner_id (شناسه‌ی تلگرام کاربری که آن را
باز کرده) در callback_data تمام دکمه‌هایش کدگذاری شده. این باعث می‌شود:
- هر بار کاربر «تسبیح» را بفرستد، یک پنل کاملاً جدید و مستقل ساخته شود.
- پنل‌های قبلی (برای همان یا کاربران دیگر) دست‌نخورده باقی بمانند.
- فقط صاحب پنل بتواند با دکمه‌های آن پنل کار کند؛ کلیک هر کاربر دیگری کاملاً بی‌پاسخ
  می‌ماند (حتی answer هم فراخوانی نمی‌شود).

تمام مراحل (صفحه‌ی اصلی <-> تأییدیه‌ی ارتقا <-> نتیجه‌ی ارتقا) با ویرایش کپشن همان یک
پیام انجام می‌شود؛ هیچ‌وقت پیام جدیدی ساخته نمی‌شود.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Update

from bot.database.engine import async_session_factory
from bot.domain.tasbih_data import get_dhikr_cooldown_for_level, get_upgrade_cost
from bot.keyboards.inline import (
    tasbih_panel_back_keyboard,
    tasbih_panel_confirm_keyboard,
    tasbih_panel_main_keyboard,
)
from bot.services.idempotency import try_claim_update
from bot.services.tasbih_service import TasbihUpgradeResult, upgrade_tasbih
from bot.services.user_service import get_or_create_user
from bot.texts import messages as texts

router = Router(name="tasbih_panel")


def _parse(data: str) -> tuple[str, int]:
    parts = data.split(":")
    action = parts[1]
    owner_id = int(parts[2])
    return action, owner_id


async def _render_main_page(callback: CallbackQuery, owner_id: int) -> None:
    async with async_session_factory() as session:
        user = await get_or_create_user(
            session, owner_id, callback.from_user.username, callback.from_user.first_name
        )
        level = user.tasbih_level
        cooldown = get_dhikr_cooldown_for_level(level)
    await callback.message.edit_caption(
        caption=texts.tasbih_panel_header(level, cooldown),
        reply_markup=tasbih_panel_main_keyboard(owner_id, level),
        parse_mode="Markdown",
    )


@router.callback_query(lambda c: c.data and c.data.startswith("tsb:"))
async def on_tasbih_panel_callback(callback: CallbackQuery, event_update: Update) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return

    action, owner_id = _parse(callback.data)

    # فقط صاحب پنل — کلیک بقیه کاملاً بدون پاسخ (نه answer، نه edit)
    if callback.from_user.id != owner_id:
        return

    if action == "main":
        async with async_session_factory() as session:
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )
            if not user.tasbih_unlocked:
                await callback.answer()
                return
        await _render_main_page(callback, owner_id)
        await callback.answer()
        return

    if action == "upgrade_ask":
        async with async_session_factory() as session:
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )
            if not user.tasbih_unlocked or user.tasbih_level >= 12:
                await callback.answer()
                return
            cost = get_upgrade_cost(user.tasbih_level)
            next_level = user.tasbih_level + 1

        await callback.message.edit_caption(
            caption=texts.tasbih_upgrade_confirm(next_level, cost),
            reply_markup=tasbih_panel_confirm_keyboard(owner_id),
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    if action == "upgrade_cancel":
        await _render_main_page(callback, owner_id)
        await callback.answer("لغو شد")
        return

    if action == "upgrade_confirm":
        async with async_session_factory() as session:
            async with session.begin():
                claimed = await try_claim_update(session, event_update.update_id)
                if not claimed:
                    await callback.answer()
                    return
                user = await get_or_create_user(
                    session, owner_id, callback.from_user.username, callback.from_user.first_name
                )
                outcome = upgrade_tasbih(user)

        await callback.answer()
        if outcome.result == TasbihUpgradeResult.SUCCESS:
            await callback.message.edit_caption(
                caption=texts.tasbih_upgrade_success(outcome.new_level, outcome.new_cooldown_seconds),
                reply_markup=tasbih_panel_back_keyboard(owner_id),
                parse_mode="Markdown",
            )
        elif outcome.result == TasbihUpgradeResult.INSUFFICIENT_NOOR:
            await callback.message.edit_caption(
                caption=texts.TASBIH_INSUFFICIENT_NOOR,
                reply_markup=tasbih_panel_back_keyboard(owner_id),
                parse_mode="Markdown",
            )
        else:
            # سطح آخر یا هنوز باز نشده -> فقط برگرد به صفحه‌ی اصلی
            await _render_main_page(callback, owner_id)
        return

    await callback.answer()
