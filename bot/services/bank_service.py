"""
سرویس بانک: شماره کارت، کارت‌به‌کارت، قرض‌الحسنه (درخواست/تأمین/بازپرداخت) و جریمه‌ی تأخیر.

همه‌ی توابع باید داخل یک تراکنش (session.begin()) صدا زده شوند.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import BankPrompt, LoanRequest, User
from bot.domain import bank_data as bd


class BankResult:
    SUCCESS = "success"
    INVALID = "invalid"
    CARD_NOT_FOUND = "card_not_found"
    SELF_TRANSFER = "self_transfer"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    AMOUNT_TOO_LOW = "amount_too_low"
    AMOUNT_TOO_HIGH = "amount_too_high"
    ALREADY_HAS_LOAN = "already_has_loan"
    LOAN_NOT_FOUND = "loan_not_found"
    OWN_LOAN = "own_loan"
    ALREADY_FUNDED = "already_funded"
    NOT_BORROWER = "not_borrower"
    NO_PROMPT = "no_prompt"


@dataclass
class BankOutcome:
    result: str
    detail: int = 0
    other_telegram_id: int | None = None  # برای اطلاع‌رسانی به طرف مقابل


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# شماره کارت
# ---------------------------------------------------------------------------


async def ensure_card_number(session: AsyncSession, user: User) -> str:
    if user.card_number:
        return user.card_number
    for _ in range(20):
        digits = bd.generate_card_digits()
        exists = (
            await session.execute(select(User.id).where(User.card_number == digits))
        ).scalar_one_or_none()
        if exists is None:
            user.card_number = digits
            await session.flush()
            return digits
    raise RuntimeError("امکان ساخت شماره کارت یکتا نبود")


# ---------------------------------------------------------------------------
# زندان
# ---------------------------------------------------------------------------


def jail_remaining_seconds(user: User, now: datetime | None = None) -> int:
    until = _aware(user.jail_until)
    if until is None:
        return 0
    now = now or _now()
    return max(0, int((until - now).total_seconds()))


# ---------------------------------------------------------------------------
# کارت به کارت
# ---------------------------------------------------------------------------


async def transfer_by_card(
    session: AsyncSession, sender: User, card_digits: str, amount: int
) -> BankOutcome:
    if amount < 1:
        return BankOutcome(BankResult.INVALID)
    recipient = (
        await session.execute(select(User).where(User.card_number == card_digits))
    ).scalar_one_or_none()
    if recipient is None:
        return BankOutcome(BankResult.CARD_NOT_FOUND)
    if recipient.id == sender.id:
        return BankOutcome(BankResult.SELF_TRANSFER)
    if sender.toman < amount:
        return BankOutcome(BankResult.INSUFFICIENT_FUNDS, amount - sender.toman)

    sender.toman -= amount
    recipient.toman += amount
    await session.flush()
    return BankOutcome(BankResult.SUCCESS, amount, other_telegram_id=recipient.telegram_id)


# ---------------------------------------------------------------------------
# قرض‌الحسنه
# ---------------------------------------------------------------------------


async def get_active_loan(session: AsyncSession, user: User) -> LoanRequest | None:
    row = await session.execute(
        select(LoanRequest)
        .where(LoanRequest.borrower_id == user.id, LoanRequest.status != "repaid")
        .order_by(LoanRequest.id.desc())
    )
    return row.scalars().first()


async def request_loan(session: AsyncSession, user: User, amount: int) -> BankOutcome:
    if amount < bd.LOAN_MIN_AMOUNT:
        return BankOutcome(BankResult.AMOUNT_TOO_LOW, bd.LOAN_MIN_AMOUNT)
    if amount > bd.LOAN_MAX_AMOUNT:
        return BankOutcome(BankResult.AMOUNT_TOO_HIGH, bd.LOAN_MAX_AMOUNT)
    if await get_active_loan(session, user) is not None:
        return BankOutcome(BankResult.ALREADY_HAS_LOAN)

    session.add(
        LoanRequest(
            borrower_id=user.id,
            amount=amount,
            repay_amount=bd.repay_amount_for(amount),
            lender_noor_reward=bd.lender_noor_reward_for(amount),
            status="pending",
            requested_at=_now(),
        )
    )
    await session.flush()
    return BankOutcome(BankResult.SUCCESS, amount)


async def list_open_loans(session: AsyncSession, exclude_user_id: int | None = None):
    """[(LoanRequest, borrower_name)] برای پنل «وام‌های درخواستی»."""
    query = (
        select(LoanRequest, User)
        .join(User, User.id == LoanRequest.borrower_id)
        .where(LoanRequest.status == "pending")
        .order_by(LoanRequest.id)
        .limit(bd.MAX_LOANS_LISTED)
    )
    if exclude_user_id is not None:
        query = query.where(LoanRequest.borrower_id != exclude_user_id)
    rows = await session.execute(query)
    return [(l, (u.first_name or u.username or "کاربر")) for l, u in rows.all()]


async def get_my_debts(session: AsyncSession, user: User) -> list[LoanRequest]:
    rows = await session.execute(
        select(LoanRequest)
        .where(LoanRequest.borrower_id == user.id, LoanRequest.status == "funded")
        .order_by(LoanRequest.id)
    )
    return list(rows.scalars())


async def fund_loan(session: AsyncSession, lender: User, loan_id: int) -> BankOutcome:
    loan = await session.get(LoanRequest, loan_id)
    if loan is None or loan.status != "pending":
        return BankOutcome(BankResult.LOAN_NOT_FOUND)
    if loan.borrower_id == lender.id:
        return BankOutcome(BankResult.OWN_LOAN)
    if lender.toman < loan.amount:
        return BankOutcome(BankResult.INSUFFICIENT_FUNDS, loan.amount - lender.toman)

    borrower = await session.get(User, loan.borrower_id)
    lender.toman -= loan.amount
    borrower.toman += loan.amount
    lender.noor_current += loan.lender_noor_reward
    lender.noor_total_earned += loan.lender_noor_reward

    loan.status = "funded"
    loan.lender_id = lender.id
    loan.funded_at = _now()
    loan.due_at = _now() + timedelta(hours=bd.LOAN_DUE_HOURS)
    await session.flush()
    return BankOutcome(
        BankResult.SUCCESS, loan.amount, other_telegram_id=borrower.telegram_id if borrower else None
    )


async def repay_loan(session: AsyncSession, user: User, loan_id: int) -> BankOutcome:
    loan = await session.get(LoanRequest, loan_id)
    if loan is None or loan.status != "funded":
        return BankOutcome(BankResult.LOAN_NOT_FOUND)
    if loan.borrower_id != user.id:
        return BankOutcome(BankResult.NOT_BORROWER)
    if user.toman < loan.repay_amount:
        return BankOutcome(BankResult.INSUFFICIENT_FUNDS, loan.repay_amount - user.toman)

    lender = await session.get(User, loan.lender_id) if loan.lender_id else None
    user.toman -= loan.repay_amount
    if lender is not None:
        lender.toman += loan.repay_amount
    loan.status = "repaid"
    loan.repaid_at = _now()
    await session.flush()
    return BankOutcome(
        BankResult.SUCCESS,
        loan.repay_amount,
        other_telegram_id=lender.telegram_id if lender else None,
    )


# ---------------------------------------------------------------------------
# جریمه‌ی تأخیر در بازپرداخت (برای scheduler)
# ---------------------------------------------------------------------------


@dataclass
class LoanPenalty:
    user: User
    kind: str  # 'noor' | 'toman' | 'jail'
    detail: int  # مقدار کم‌شده یا ساعت زندان


async def apply_due_penalties(
    session: AsyncSession, now: datetime | None = None, rng: random.Random | None = None
) -> list[LoanPenalty]:
    """
    وام‌های سررسیدگذشته‌ی پرداخت‌نشده را پیدا می‌کند و اگر از آخرین جریمه ۲۴ ساعت گذشته
    باشد (یا اصلاً جریمه نشده)، یکی از سه جریمه را تصادفی اعمال می‌کند. بدهی پابرجا می‌ماند.
    """
    now = now or _now()
    rng = rng or random
    penalties: list[LoanPenalty] = []

    rows = await session.execute(
        select(LoanRequest).where(LoanRequest.status == "funded", LoanRequest.due_at.is_not(None))
    )
    for loan in rows.scalars():
        due_at = _aware(loan.due_at)
        if due_at is None or now < due_at:
            continue
        last = _aware(loan.last_penalty_at)
        if last is not None and now - last < timedelta(hours=bd.LOAN_PENALTY_RECHECK_HOURS):
            continue

        borrower = await session.get(User, loan.borrower_id)
        if borrower is None:
            continue

        kind = rng.choice(("noor", "toman", "jail"))
        if kind == "noor":
            amount = max(1, int(borrower.noor_current * bd.LOAN_PENALTY_NOOR_PERCENT))
            borrower.noor_current = max(0, borrower.noor_current - amount)
            penalties.append(LoanPenalty(borrower, "noor", amount))
        elif kind == "toman":
            amount = max(1, int(borrower.toman * bd.LOAN_PENALTY_TOMAN_PERCENT))
            borrower.toman = max(0, borrower.toman - amount)
            penalties.append(LoanPenalty(borrower, "toman", amount))
        else:
            extension = timedelta(hours=bd.LOAN_PENALTY_JAIL_HOURS)
            current = _aware(borrower.jail_until)
            base = current if current and current > now else now
            borrower.jail_until = base + extension
            penalties.append(LoanPenalty(borrower, "jail", bd.LOAN_PENALTY_JAIL_HOURS))

        loan.last_penalty_at = now

    if penalties:
        await session.flush()
    return penalties


# ---------------------------------------------------------------------------
# ورود متنی با ریپلای (کارت به کارت / مبلغ وام)
# ---------------------------------------------------------------------------


async def set_prompt(
    session: AsyncSession, user: User, kind: str, chat_id: int, message_id: int
) -> None:
    await session.execute(delete(BankPrompt).where(BankPrompt.user_id == user.id))
    session.add(
        BankPrompt(user_id=user.id, kind=kind, chat_id=chat_id, message_id=message_id, created_at=_now())
    )
    await session.flush()


async def get_prompt(session: AsyncSession, user: User, ttl_minutes: int = 30) -> BankPrompt | None:
    prompt = (
        await session.execute(select(BankPrompt).where(BankPrompt.user_id == user.id))
    ).scalar_one_or_none()
    if prompt is None:
        return None
    created = _aware(prompt.created_at)
    if _now() - created > timedelta(minutes=ttl_minutes):
        await session.delete(prompt)
        await session.flush()
        return None
    return prompt


async def clear_prompt(session: AsyncSession, user: User) -> None:
    await session.execute(delete(BankPrompt).where(BankPrompt.user_id == user.id))
    await session.flush()
