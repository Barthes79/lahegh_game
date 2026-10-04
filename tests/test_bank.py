"""تست‌های بانک (Level 3). اجرا: python tests/test_bank.py"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_PATH"] = "/tmp/test_laahiq_bank.db"
os.environ.setdefault("BOT_TOKEN", "dummy:token")

DB_PATH = os.environ["DATABASE_PATH"]
for suffix in ("", "-wal", "-shm"):
    if os.path.exists(DB_PATH + suffix):
        os.remove(DB_PATH + suffix)

from bot.database.engine import async_session_factory, run_migrations  # noqa: E402
from bot.domain import bank_data as bd  # noqa: E402
from bot.services import bank_service as bs  # noqa: E402
from bot.services.activity_service import OutcomeStatus, process_activity  # noqa: E402
from bot.services.bank_service import BankResult  # noqa: E402
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id  # noqa: E402


def check(cond: bool, label: str) -> None:
    print(f"[{'OK  ' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(f"TEST FAILED: {label}")


async def with_user(tg: int, fn):
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(session, tg, f"u{tg}", f"U{tg}")
            return await fn(session, user)


async def ret(v):
    return v


async def main() -> None:
    await run_migrations()

    print("\n== شماره کارت ==")
    c1 = await with_user(1, lambda s, u: bs.ensure_card_number(s, u))
    c1_again = await with_user(1, lambda s, u: bs.ensure_card_number(s, u))
    c2 = await with_user(2, lambda s, u: bs.ensure_card_number(s, u))
    check(len(c1) == 16 and c1.isdigit(), "شماره کارت ۱۶ رقمی است")
    check(c1 == c1_again, "شماره کارت یک کاربر ثابت می‌ماند")
    check(c1 != c2, "شماره کارت کاربران یکتاست")

    print("\n== کارت به کارت ==")
    async def _set_toman(s, u):
        u.toman = 20000
    await with_user(1, _set_toman)

    async def _self(s, u):
        return await bs.transfer_by_card(s, u, c1, 100)
    check((await with_user(1, _self)).result == BankResult.SELF_TRANSFER, "انتقال به کارت خود رد می‌شود")

    async def _bad_card(s, u):
        return await bs.transfer_by_card(s, u, "0" * 16, 100)
    check((await with_user(1, _bad_card)).result == BankResult.CARD_NOT_FOUND, "کارت ناموجود رد می‌شود")

    async def _poor(s, u):
        return await bs.transfer_by_card(s, u, c2, 999999)
    r = await with_user(1, _poor)
    check(r.result == BankResult.INSUFFICIENT_FUNDS, "انتقال بیش از موجودی رد می‌شود")

    async def _ok(s, u):
        before = u.toman
        r = await bs.transfer_by_card(s, u, c2, 5000)
        return r, before - u.toman
    r, spent = await with_user(1, _ok)
    check(r.result == BankResult.SUCCESS and spent == 5000 and r.other_telegram_id == 2, "انتقال موفق")
    bal2 = await with_user(2, lambda s, u: ret(u.toman))
    check(bal2 == 5000, "مبلغ به گیرنده رسید")

    print("\n== قرض‌الحسنه: درخواست ==")
    async def _low(s, u):
        return await bs.request_loan(s, u, bd.LOAN_MIN_AMOUNT - 1)
    r = await with_user(3, _low)
    check(r.result == BankResult.AMOUNT_TOO_LOW and r.detail == bd.LOAN_MIN_AMOUNT, "وام زیر حداقل رد می‌شود")

    async def _high(s, u):
        return await bs.request_loan(s, u, bd.LOAN_MAX_AMOUNT + 1)
    r = await with_user(3, _high)
    check(r.result == BankResult.AMOUNT_TOO_HIGH and r.detail == bd.LOAN_MAX_AMOUNT, "وام بالای حداکثر رد می‌شود")

    AMOUNT = 10000
    async def _req(s, u):
        r1 = await bs.request_loan(s, u, AMOUNT)
        r2 = await bs.request_loan(s, u, AMOUNT)  # درخواست دوم وقتی هنوز فعال دارد
        return r1, r2
    r1, r2 = await with_user(3, _req)
    check(r1.result == BankResult.SUCCESS, "درخواست وام موفق")
    check(r2.result == BankResult.ALREADY_HAS_LOAN, "درخواست دوم هم‌زمان رد می‌شود")

    print("\n== قرض‌الحسنه: تأمین وام ==")
    async def _get_loan(s, u):
        return (await bs.get_active_loan(s, u)).id
    loan_id = await with_user(3, _get_loan)

    async def _own(s, u):
        return (await bs.fund_loan(s, u, loan_id)).result
    check(await with_user(3, _own) == BankResult.OWN_LOAN, "تأمین وام خود ممنوع است")

    async def _open_list(s, u):
        return await bs.list_open_loans(s, exclude_user_id=u.id)
    lst = await with_user(4, _open_list)
    check(any(l.id == loan_id for l, _ in lst), "وام در لیست وام‌های درخواستی دیده می‌شود")

    async def _poor_fund(s, u):
        u.toman = 1
        r = await bs.fund_loan(s, u, loan_id)
        u.toman = 99999
        return r
    check((await with_user(4, _poor_fund)).result == BankResult.INSUFFICIENT_FUNDS, "تأمین وام با پول ناکافی رد می‌شود")

    async def _fund(s, u):
        u.toman = 99999
        before_toman, before_noor = u.toman, u.noor_current
        r = await bs.fund_loan(s, u, loan_id)
        return r, before_toman - u.toman, u.noor_current - before_noor
    r, spent, noor_gain = await with_user(4, _fund)
    check(r.result == BankResult.SUCCESS and spent == AMOUNT, "تأمین وام موفق؛ مبلغ از حساب وام‌دهنده کم شد")
    check(noor_gain == bd.lender_noor_reward_for(AMOUNT) and noor_gain > 0, "وام‌دهنده همون لحظه نور می‌گیرد")
    borrower_toman = await with_user(3, lambda s, u: ret(u.toman))
    check(borrower_toman >= AMOUNT, "مبلغ وام به وام‌گیرنده رسید")

    async def _fund_again(s, u):
        return (await bs.fund_loan(s, u, loan_id)).result
    check(await with_user(5, _fund_again) == BankResult.LOAN_NOT_FOUND, "وام تأمین‌شده دیگر pending نیست")

    print("\n== قرض‌الحسنه: بازپرداخت ==")
    async def _debts(s, u):
        return await bs.get_my_debts(s, u)
    debts = await with_user(3, _debts)
    check(len(debts) == 1 and debts[0].repay_amount == bd.repay_amount_for(AMOUNT), "بدهی با مبلغ بازپرداخت درست ثبت شده")

    async def _wrong_payer(s, u):
        return (await bs.repay_loan(s, u, loan_id)).result
    check(await with_user(4, _wrong_payer) == BankResult.NOT_BORROWER, "فقط بدهکار می‌تواند بدهی را پرداخت کند")

    async def _poor_repay(s, u):
        u.toman = 0
        r = await bs.repay_loan(s, u, loan_id)
        return r
    check((await with_user(3, _poor_repay)).result == BankResult.INSUFFICIENT_FUNDS, "بازپرداخت با پول ناکافی رد می‌شود")

    async def _repay(s, u):
        u.toman = bd.repay_amount_for(AMOUNT) + 500
        before = u.toman
        r = await bs.repay_loan(s, u, loan_id)
        return r, before - u.toman
    r, spent = await with_user(3, _repay)
    check(r.result == BankResult.SUCCESS and spent == bd.repay_amount_for(AMOUNT), "بازپرداخت موفق؛ مبلغ بیشتر از اصل وام")
    lender_toman = await with_user(4, lambda s, u: ret(u.toman))
    check(r.other_telegram_id == 4, "بازپرداخت به وام‌دهنده اطلاع داده می‌شود")

    async def _repay_again(s, u):
        return (await bs.repay_loan(s, u, loan_id)).result
    check(await with_user(3, _repay_again) == BankResult.LOAN_NOT_FOUND, "بدهیِ پرداخت‌شده دوباره قابل پرداخت نیست")

    async def _new_after_repay(s, u):
        return (await bs.request_loan(s, u, AMOUNT)).result
    check(await with_user(3, _new_after_repay) == BankResult.SUCCESS, "بعد از پرداخت کامل، وام جدید مجاز است")

    print("\n== جریمه‌ی تأخیر ==")
    async def _setup_overdue(s, u):
        u.toman = 99999
        await bs.request_loan(s, u, AMOUNT)
        loan = await bs.get_active_loan(s, u)
        return loan.id
    lid2 = await with_user(6, _setup_overdue)

    async def _fund2(s, u):
        u.toman = 99999
        r = await bs.fund_loan(s, u, lid2)
        return r
    await with_user(4, _fund2)

    from bot.database.models import LoanRequest

    async def _make_overdue(s, u):
        loan = await s.get(LoanRequest, lid2)
        loan.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await with_user(6, _make_overdue)

    rng_noor = random.Random(0)
    for _ in range(50):
        if rng_noor.choice(("noor", "toman", "jail")) == "noor":
            break
    rng = random.Random(0)
    async with async_session_factory() as session:
        async with session.begin():
            penalties = await bs.apply_due_penalties(session, rng=rng)
    check(len(penalties) == 1 and penalties[0].kind in ("noor", "toman", "jail"), "جریمه‌ی سررسیدگذشته اعمال شد")
    kind_applied = penalties[0].kind

    async with async_session_factory() as session:
        async with session.begin():
            again = await bs.apply_due_penalties(session, rng=rng)
    check(len(again) == 0, "قبل از گذشت ۲۴ ساعت دوباره جریمه نمی‌شود")

    borrower_debts_after = await with_user(6, _debts)
    check(len(borrower_debts_after) == 1, "با وجود جریمه، بدهی همچنان پابرجاست")

    if kind_applied == "jail":
        jail_until = await with_user(6, lambda s, u: ret(u.jail_until))
        check(jail_until is not None, "جریمه‌ی زندان jail_until را تنظیم کرد")

    print("\n== زندان و ثبت ذکر ==")
    async def _jail_now(s, u):
        u.jail_until = datetime.now(timezone.utc) + timedelta(hours=2)
        u.game_started = True
    await with_user(7, _jail_now)

    async def act(tg, text, upd):
        async with async_session_factory() as session:
            async with session.begin():
                return await process_activity(
                    session, update_id=upd, telegram_id=tg, username=f"u{tg}", first_name=f"U{tg}",
                    chat_id=-99, raw_text=text,
                )
    out = await act(7, "الحمدلله", 5001)
    check(out.status == OutcomeStatus.JAILED and out.jail_remaining_seconds > 0, "کاربر زندانی نمی‌تواند ذکر ثبت کند")

    async def _free(s, u):
        u.jail_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await with_user(7, _free)
    out = await act(7, "الحمدلله", 5002)
    check(out.status == OutcomeStatus.SUCCESS, "بعد از پایان زندان، ذکر عادی ثبت می‌شود")

    print("\n== پارس شماره کارت ==")
    check(bd.normalize_card_number("6219-6756-3058-1121") == "6219675630581121", "پارس شماره کارت با خط‌تیره")
    check(bd.normalize_card_number("۶۲۱۹ ۶۷۵۶ ۳۰۵۸ ۱۱۲۱") == "6219675630581121", "پارس شماره کارت فارسی با فاصله")
    check(bd.normalize_card_number("12345") is None, "شماره کارت با طول اشتباه رد می‌شود")

    print("\n== پنل‌ها (رندر) ==")
    from bot.handlers import bank_panel as bp

    async def _panels(s, u):
        home = await bp.page_home(s, u)
        transfer = await bp.page_transfer(s, u, -1, 1)
        loan_page = await bp.page_loan(s, u, -1, 2)
        debts_page = await bp.page_debts(s, u)
        requested_page = await bp.page_requested(s, u)
        return home, transfer, loan_page, debts_page, requested_page
    pages = await with_user(8, _panels)
    check(all(t for t, _ in pages), "همه‌ی صفحه‌های بانک متن دارند")
    check(
        all(len(b.callback_data.encode()) <= 64 for _, k in pages for r in k.inline_keyboard for b in r),
        "callback_data همه‌ی دکمه‌ها زیر ۶۴ بایت است",
    )

    print("\n== ورود متن با ریپلای (شبیه‌سازی هندلر) ==")
    from unittest.mock import AsyncMock, MagicMock

    def msg(text, user_id, reply_mid, chat=-5):
        m = MagicMock()
        m.text = text
        m.from_user.id = user_id
        m.from_user.is_bot = False
        m.from_user.username = "a"
        m.from_user.first_name = "A"
        m.chat.id = chat
        m.reply_to_message.message_id = reply_mid
        m.reply = AsyncMock()
        m.bot.send_message = AsyncMock()
        return m

    uid = [9000]

    def upd():
        uid[0] += 1
        return MagicMock(update_id=uid[0])

    async def _prep(s, u):
        u.toman = 50000

    await with_user(20, _prep)
    c20 = await with_user(20, lambda s, u: ret(u.card_number))
    async with async_session_factory() as session:
        async with session.begin():
            u = await get_user_by_telegram_id(session, 20)
            await bs.set_prompt(session, u, "transfer", -5, 77)

    m = msg("abc", 20, 77)
    check(await bp.try_handle_bank_reply(m, upd()) is True, "ریپلای روی پیام درست پردازش می‌شود")
    check("فرمت درست نیست" in m.reply.await_args.args[0], "فرمت غلط خطا می‌دهد و prompt می‌ماند")

    m = msg(f"{bd.format_card_number(c2)} 1000", 20, 77)
    await bp.try_handle_bank_reply(m, upd())
    check("واریز شد" in m.reply.await_args.args[0], "کارت‌به‌کارت با فرمت خط‌تیره‌دار کار می‌کند")
    check(m.bot.send_message.await_args.kwargs["chat_id"] == 2, "گیرنده مطلع می‌شود")

    m = msg("سلام چطوری", 20, 999)
    check(await bp.try_handle_bank_reply(m, upd()) is False, "ریپلای روی پیام دیگر نادیده گرفته می‌شود")

    print("\nALL BANK TESTS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
