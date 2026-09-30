"""
هندلر پنل «بانک»: کارت به کارت، قرض‌الحسنه، بدهی‌ها، وام‌های درخواستی.

مثل پنل‌های شغل/فروشگاه: هر «بانک» یک پنل مستقل می‌سازد، owner_id داخل callback_data است
و کلیک بقیه‌ی کاربران کاملاً بی‌پاسخ می‌ماند. ورودی متنی (شماره کارت+مبلغ / مبلغ وام) با
ریپلای روی پیام پنل گرفته می‌شود (bot/database/models.py: BankPrompt).

callback_data: bank:<action>:<owner_id>
  home | transfer | loan | debts | pay:<loan_id> | requested | fund:<loan_id>
"""
from __future__ import annotations

import logging
import re

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update

from bot.database.engine import async_session_factory
from bot.database.models import LoanRequest, User
from bot.domain import bank_data as bd
from bot.services import bank_service as bs
from bot.services.bank_service import BankResult
from bot.services.idempotency import try_claim_update
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id
from bot.texts import bank_texts as bt
from bot.handlers.store_panel import parse_price  # پارسر عدد فارسی/کاما مشترک

logger = logging.getLogger(__name__)

router = Router(name="bank_panel")


def _btn(text: str, owner_id: int, action: str, *args: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=":".join(["bank", action, str(owner_id), *args]))


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _home_row(owner_id: int) -> list[InlineKeyboardButton]:
    return [_btn("🔙 بانک", owner_id, "home")]


# ---------------------------------------------------------------------------
# صفحه‌ها
# ---------------------------------------------------------------------------


async def page_home(session, user: User):
    o = user.telegram_id
    card = await bs.ensure_card_number(session, user)
    debts = await bs.get_my_debts(session, user)
    rows = [
        [_btn("💳 کارت به کارت", o, "transfer")],
        [_btn("🤝 قرض‌الحسنه", o, "loan")],
        [_btn(f"📄 بدهی‌ها ({len(debts)})", o, "debts")],
        [_btn("📋 وام‌های درخواستی", o, "requested")],
    ]
    return bt.bank_home(user.toman, card, len(debts)), _kb(rows)


async def page_transfer(session, user: User, chat_id: int, message_id: int):
    o = user.telegram_id
    await bs.set_prompt(session, user, "transfer", chat_id, message_id)
    return bt.transfer_prompt_page(user.toman), _kb([_home_row(o)])


async def page_loan(session, user: User, chat_id: int, message_id: int):
    o = user.telegram_id
    active = await bs.get_active_loan(session, user)
    if active is not None:
        return bt.loan_home_active(active), _kb([_home_row(o)])
    await bs.set_prompt(session, user, "loan", chat_id, message_id)
    return bt.loan_home_no_active(), _kb([_home_row(o)])


async def page_debts(session, user: User):
    o = user.telegram_id
    debts = await bs.get_my_debts(session, user)
    rows = [[_btn(f"💳 پرداخت {d.repay_amount:,}", o, "pay", str(d.id))] for d in debts]
    rows.append(_home_row(o))
    return bt.debts_page(user.toman, debts), _kb(rows)


async def page_requested(session, user: User):
    o = user.telegram_id
    loans = await bs.list_open_loans(session, exclude_user_id=user.id)
    rows = [
        [_btn(f"🤝 پرداخت وام {l.amount:,} به {name[:12]}", o, "fund", str(l.id))]
        for l, name in loans
    ]
    rows.append(_home_row(o))
    return bt.requested_loans_page(loans, user.toman), _kb(rows)


# ---------------------------------------------------------------------------
# دستور متنی «بانک»
# ---------------------------------------------------------------------------


async def show_bank_panel(message: Message) -> None:
    if message.from_user is None:
        return
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(
                session, message.from_user.id, message.from_user.username, message.from_user.first_name
            )
            text, kb = await page_home(session, user)
    await message.reply(text, reply_markup=kb)


# ---------------------------------------------------------------------------
# کارت‌به‌کارت مستقیم: فقط نوشتن «شماره‌کارت مبلغ» در چت (بدون پنل و بدون ریپلای)
# ---------------------------------------------------------------------------

# کاندیدهای ۱۶ رقمی (ارقام فارسی/انگلیسی) که می‌توانند با فاصله یا خط‌تیره گروه‌بندی شده باشند.
# lookahead باعث می‌شود کاندیدهای هم‌پوشان هم بررسی شوند (مثلاً مبلغ قبل از شماره کارت).
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?=(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4})(?!\d))")


def parse_direct_transfer(text: str) -> tuple[str, int] | None:
    """
    «6219-6756-3058-1121 5000» یا «5000 6219675630581121» -> (۱۶ رقم کارت، مبلغ).
    اگر متن دقیقاً از یک شماره کارت + یک مبلغ تشکیل نشده باشد None برمی‌گرداند تا پیام‌های
    عادی گروه هرگز به‌عنوان انتقال پول برداشت نشوند. این تابع به دیتابیس دست نمی‌زند.
    کارت معتبر باید با پیشوند کارت‌های بازی (bd.CARD_BIN) شروع شود؛ این کار مبهم‌بودن
    «مبلغ + کارت» را از بین می‌برد.
    """
    if not text:
        return None
    translated = text.translate(bd._CARD_DIGIT_TRANSLATE)
    for match in _CARD_CANDIDATE.finditer(translated):
        raw = match.group(1)
        digits = bd.normalize_card_number(raw)
        if digits is None or not digits.startswith(bd.CARD_BIN):
            continue
        start = match.start()
        rest = (translated[:start] + " " + translated[start + len(raw) :]).strip()
        if not rest:
            return None  # فقط شماره کارت (مثلاً کسی کارت خودش را فرستاده) -> نادیده بگیر
        amount = parse_price(rest)
        if amount is not None:
            return digits, amount
    return None


async def _run_transfer(
    session, message: Message, user: User, digits: str, amount: int
) -> tuple[str, bool, tuple[int, str] | None]:
    """انتقال را انجام می‌دهد؛ (متن پاسخ، موفق بودن، اطلاع‌رسانی به گیرنده) را برمی‌گرداند."""
    out = await bs.transfer_by_card(session, user, digits, amount)
    if out.result == BankResult.SUCCESS:
        name = message.from_user.first_name or message.from_user.username or "یک کاربر"
        return (
            bt.transfer_success(out.detail),
            True,
            (out.other_telegram_id, bt.transfer_received_notice(name, out.detail)),
        )
    if out.result == BankResult.CARD_NOT_FOUND:
        return bt.TRANSFER_CARD_NOT_FOUND, False, None
    if out.result == BankResult.SELF_TRANSFER:
        return bt.TRANSFER_SELF, False, None
    if out.result == BankResult.INSUFFICIENT_FUNDS:
        return bt.transfer_insufficient(out.detail), False, None
    return bt.TRANSFER_BAD_FORMAT, False, None


async def try_handle_direct_transfer(message: Message, event_update: Update) -> bool:
    """
    پیام شامل «شماره‌کارت + مبلغ» را بدون نیاز به پنل/ریپلای انتقال می‌دهد (گروه و PV).
    True یعنی پیام مصرف شد و دیگر نباید به‌عنوان صلوات/ذکر بررسی شود.
    """
    if message.from_user is None or not message.text:
        return False
    parsed = parse_direct_transfer(message.text)  # بدون دیتابیس؛ پیام‌های عادی همین‌جا رد می‌شوند
    if parsed is None:
        return False
    digits, amount = parsed

    notify: tuple[int, str] | None = None
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user is None:
                return False
            if not await try_claim_update(session, event_update.update_id):
                return True
            reply_text, _ok, notify = await _run_transfer(session, message, user, digits, amount)

    await message.reply(reply_text)
    if notify is not None and notify[0]:
        try:
            await message.bot.send_message(chat_id=notify[0], text=notify[1])
        except Exception:  # noqa: BLE001
            logger.debug("اطلاع‌رسانی واریز به گیرنده ناموفق بود", exc_info=True)
    return True


# ---------------------------------------------------------------------------
# ورود متنی با ریپلای (کارت‌به‌کارت / مبلغ وام)
# ---------------------------------------------------------------------------


async def try_handle_bank_reply(message: Message, event_update: Update) -> bool:
    if message.reply_to_message is None or message.from_user is None or not message.text:
        return False

    notify: tuple[int, str] | None = None
    handled = False
    reply_text: str | None = None

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user is None:
                return False
            prompt = await bs.get_prompt(session, user)
            if (
                prompt is None
                or prompt.chat_id != message.chat.id
                or prompt.message_id != message.reply_to_message.message_id
            ):
                return False

            if not await try_claim_update(session, event_update.update_id):
                return True
            handled = True

            if prompt.kind == "transfer":
                parts = message.text.split()
                amount = parse_price(parts[-1]) if len(parts) >= 2 else None
                card_raw = " ".join(parts[:-1]) if len(parts) >= 2 else ""
                digits = bd.normalize_card_number(card_raw) if card_raw else None
                if digits is None or amount is None:
                    reply_text = bt.TRANSFER_BAD_FORMAT
                else:
                    reply_text, ok, notify = await _run_transfer(
                        session, message, user, digits, amount
                    )
                    if ok:
                        await bs.clear_prompt(session, user)

            elif prompt.kind == "loan":
                amount = parse_price(message.text)
                if amount is None:
                    reply_text = bt.LOAN_NOT_A_NUMBER
                else:
                    out = await bs.request_loan(session, user, amount)
                    if out.result == BankResult.SUCCESS:
                        await bs.clear_prompt(session, user)
                        reply_text = bt.loan_requested(amount)
                    elif out.result == BankResult.AMOUNT_TOO_LOW:
                        reply_text = bt.loan_amount_too_low(out.detail)
                    elif out.result == BankResult.AMOUNT_TOO_HIGH:
                        reply_text = bt.loan_amount_too_high(out.detail)
                    else:
                        await bs.clear_prompt(session, user)
                        reply_text = bt.ALREADY_HAS_LOAN

    if handled and reply_text:
        await message.reply(reply_text)
    if notify is not None and notify[0]:
        try:
            await message.bot.send_message(chat_id=notify[0], text=notify[1])
        except Exception:  # noqa: BLE001
            logger.debug("اطلاع‌رسانی واریز به گیرنده ناموفق بود", exc_info=True)
    return handled


# ---------------------------------------------------------------------------
# callbackها
# ---------------------------------------------------------------------------


async def _edit(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        logger.warning("edit_text failed, sending new message instead: %s", exc)
        try:
            await callback.message.answer(text, reply_markup=kb)
        except Exception:  # noqa: BLE001
            logger.exception("ارسال پیام جایگزین هم ناموفق بود")


@router.callback_query(lambda c: c.data and c.data.startswith("bank:"))
async def on_bank_callback(callback: CallbackQuery, event_update: Update) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
        return
    action, owner_id, args = parts[1], int(parts[2]), parts[3:]
    if callback.from_user.id != owner_id:
        return

    notify: tuple[int, str] | None = None
    toast: str | None = None

    async with async_session_factory() as session:
        async with session.begin():
            if not await try_claim_update(session, event_update.update_id):
                await callback.answer()
                return
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )

            page = None
            chat_id, message_id = callback.message.chat.id, callback.message.message_id

            if action == "home":
                await bs.clear_prompt(session, user)
                page = await page_home(session, user)

            elif action == "transfer":
                page = await page_transfer(session, user, chat_id, message_id)

            elif action == "loan":
                page = await page_loan(session, user, chat_id, message_id)

            elif action == "debts":
                page = await page_debts(session, user)

            elif action == "pay" and args and args[0].isdigit():
                out = await bs.repay_loan(session, user, int(args[0]))
                if out.result == BankResult.SUCCESS:
                    toast = bt.repay_success(out.detail)
                    if out.other_telegram_id:
                        name = callback.from_user.first_name or callback.from_user.username or "یک کاربر"
                        notify = (out.other_telegram_id, bt.repay_notice_to_lender(name, out.detail))
                elif out.result == BankResult.INSUFFICIENT_FUNDS:
                    toast = bt.insufficient_funds(out.detail)
                else:
                    toast = bt.LOAN_GONE
                page = await page_debts(session, user)

            elif action == "requested":
                page = await page_requested(session, user)

            elif action == "fund" and args and args[0].isdigit():
                loan_id = int(args[0])
                loan_before = await session.get(LoanRequest, loan_id)
                noor_reward = loan_before.lender_noor_reward if loan_before else 0
                out = await bs.fund_loan(session, user, loan_id)
                if out.result == BankResult.SUCCESS:
                    toast = bt.fund_success(out.detail, noor_reward)
                    if out.other_telegram_id:
                        name = callback.from_user.first_name or callback.from_user.username or "یک کاربر"
                        notify = (out.other_telegram_id, bt.fund_notice_to_borrower(name, out.detail))
                elif out.result == BankResult.INSUFFICIENT_FUNDS:
                    toast = bt.insufficient_funds(out.detail)
                elif out.result == BankResult.OWN_LOAN:
                    toast = "این وام خودته."
                else:
                    toast = bt.LOAN_GONE
                page = await page_requested(session, user)

            if page is None:
                page = await page_home(session, user)
            text, kb = page

    await callback.answer(toast, show_alert=bool(toast) and len(toast) > 60)
    await _edit(callback, text, kb)

    if notify is not None and notify[0]:
        try:
            await callback.bot.send_message(chat_id=notify[0], text=notify[1])
        except Exception:  # noqa: BLE001
            logger.debug("اطلاع‌رسانی بانک ناموفق بود", exc_info=True)
