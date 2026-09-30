"""متن‌های نمایشی بانک (HTML، مثل بقیه‌ی پنل‌ها)."""
from __future__ import annotations

from bot.domain import bank_data as bd
from bot.database.models import LoanRequest
from bot.utils.persian_format import to_persian_digits


def _n(value: int) -> str:
    return to_persian_digits(value)


def _money(value: int) -> str:
    return f"{value:,} تومان"  # ارقام انگلیسی (قابل کپی و هماهنگ با دکمه‌ها)


def _card(digits: str) -> str:
    from bot.domain.bank_data import format_card_number

    return format_card_number(digits)  # ارقام انگلیسی تا بشود مستقیم کپی و ارسال کرد


def _hours(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{_n(h)} ساعت و {_n(m)} دقیقه"
    return f"{_n(m)} دقیقه"


# ---------------------------------------------------------------------------
# صفحه‌ی اصلی
# ---------------------------------------------------------------------------


def bank_home(toman: int, card_digits: str, debts_count: int) -> str:
    lines = [
        "🏦 <b>بانک</b>",
        "",
        f"💰 موجودی: {_money(toman)}",
        f"💳 شماره کارت: <code>{_card(card_digits)}</code>",
    ]
    if debts_count:
        lines.append(f"⚠️ {_n(debts_count)} بدهی پرداخت‌نشده داری.")
    return "\n".join(lines)


JAILED_MESSAGE_TEMPLATE = "🚫 به‌خاطر ندادن بدهی، {remaining} در زندانی و صلوات/ذکرت ثبت نمی‌شه."


def jailed_message(remaining_seconds: int) -> str:
    return JAILED_MESSAGE_TEMPLATE.format(remaining=_hours(remaining_seconds))


# ---------------------------------------------------------------------------
# کارت به کارت
# ---------------------------------------------------------------------------


def transfer_prompt_page(toman: int) -> str:
    return "\n".join(
        [
            "💳 <b>کارت به کارت</b>",
            f"💰 موجودی: {_money(toman)}",
            "",
            "👇 همین‌جا در چت، بدون ریپلای، به این شکل بنویس:",
            "<code>شماره‌کارت مبلغ</code>",
            "مثال: <code>6219-XXXX-XXXX-XXXX 5000</code>",
            "(به‌جای XXXX شماره‌ی کارت گیرنده؛ از پنل «بانک» خودِ گیرنده کپی‌اش کن)",
        ]
    )


TRANSFER_BAD_FORMAT = "⚠️ فرمت درست نیست. بنویس: شماره‌کارت مبلغ (مثال: 6219-XXXX-XXXX-XXXX 5000)"


def transfer_card_not_found(digits: str) -> str:
    return (
        f"⚠️ کارتی با شماره {bd.format_card_number(digits)} پیدا نشد.\n"
        "شماره‌کارت گیرنده رو از پنل «بانک» خودش کپی کن و دوباره بفرست."
    )


TRANSFER_SELF = "⚠️ نمی‌تونی به کارت خودت پول بفرستی."


def transfer_insufficient(missing: int) -> str:
    return f"💰 موجودی کافی نیست. {_money(missing)} کم داری."


def transfer_success(amount: int) -> str:
    return f"✅ {_money(amount)} واریز شد."


def transfer_received_notice(sender_name: str, amount: int) -> str:
    return f"💳 {sender_name} مبلغ {_money(amount)} به کارتت واریز کرد."


# ---------------------------------------------------------------------------
# قرض‌الحسنه
# ---------------------------------------------------------------------------


def loan_home_no_active() -> str:
    return "\n".join(
        [
            "🤝 <b>قرض‌الحسنه</b>",
            "",
            f"می‌تونی بین {_money(bd.LOAN_MIN_AMOUNT)} تا {_money(bd.LOAN_MAX_AMOUNT)} درخواست وام بدی.",
            f"بازپرداخت کمی بیشتر از مبلغ وامه (سهم کسی که بهت وام میده) و مهلتش {_n(bd.LOAN_DUE_HOURS)} ساعته.",
            "",
            "👇 روی همین پیام <b>ریپلای</b> کن و مبلغ مورد نظرت رو (فقط عدد) بنویس.",
        ]
    )


def loan_home_active(loan: LoanRequest) -> str:
    if loan.status == "pending":
        return "\n".join(
            [
                "🤝 <b>قرض‌الحسنه</b>",
                "",
                f"درخواست وام {_money(loan.amount)} ثبت شده و منتظر پرداخت یکی از کاربراست.",
                "می‌تونی توی «وام‌های درخواستی» ببینیش.",
            ]
        )
    return "\n".join(
        [
            "🤝 <b>قرض‌الحسنه</b>",
            "",
            f"وام {_money(loan.amount)} گرفتی و باید {_money(loan.repay_amount)} پس بدی.",
            "برای پرداخت: «بدهی‌ها»",
        ]
    )


LOAN_NOT_A_NUMBER = "⚠️ فقط یک عدد بنویس (مثلاً ۱۰۰۰۰)."


def loan_amount_too_low(minimum: int) -> str:
    return f"⚠️ حداقل مبلغ وام {_money(minimum)} است. دوباره ریپلای کن."


def loan_amount_too_high(maximum: int) -> str:
    return f"⚠️ حداکثر مبلغ وام {_money(maximum)} است. دوباره ریپلای کن."


def loan_requested(amount: int) -> str:
    return f"✅ درخواست وام {_money(amount)} ثبت شد. تا وقتی کسی پرداختش کنه توی «وام‌های درخواستی» دیده می‌شه."


ALREADY_HAS_LOAN = "⚠️ الان یک درخواست/بدهی فعال داری؛ تا تمام‌شدنش نمی‌تونی وام تازه بگیری."


# ---------------------------------------------------------------------------
# بدهی‌ها
# ---------------------------------------------------------------------------


def debts_page(toman: int, debts: list[LoanRequest]) -> str:
    lines = ["📄 <b>بدهی‌های من</b>", f"💰 موجودی: {_money(toman)}", ""]
    if not debts:
        lines.append("بدهی‌ای نداری. 🎉")
    else:
        for d in debts:
            lines.append(f"  💳 {_money(d.repay_amount)} (اصل وام: {_money(d.amount)})")
        lines.append("")
        lines.append("دیرکردن مهلت باعث جریمه (کم‌شدن نور/پول یا چند ساعت زندان) می‌شه.")
    return "\n".join(lines)


def repay_success(amount: int) -> str:
    return f"✅ بدهی {_money(amount)} پرداخت شد."


def repay_notice_to_lender(borrower_name: str, amount: int) -> str:
    return f"🤝 {borrower_name} بدهی‌اش رو پرداخت کرد و {_money(amount)} به حسابت اضافه شد."


# ---------------------------------------------------------------------------
# وام‌های درخواستی
# ---------------------------------------------------------------------------


def requested_loans_page(loans: list[tuple[LoanRequest, str]], toman: int) -> str:
    lines = ["📋 <b>وام‌های درخواستی</b>", f"💰 موجودی: {_money(toman)}", ""]
    if not loans:
        lines.append("الان کسی درخواست وام نداره.")
    else:
        lines.append("با پرداخت وام یکی از این‌ها، همون لحظه نور می‌گیری:")
        for loan, name in loans:
            lines.append(
                f"  👤 {name} — {_money(loan.amount)} (پاداش نور تو: {_n(loan.lender_noor_reward)})"
            )
    return "\n".join(lines)


def fund_success(amount: int, noor_reward: int) -> str:
    return f"✅ {_money(amount)} پرداخت شد و {_n(noor_reward)} نور گرفتی."


def fund_notice_to_borrower(lender_name: str, amount: int) -> str:
    return f"🤝 {lender_name} وامت رو پرداخت کرد و {_money(amount)} به حسابت اضافه شد."


LOAN_GONE = "این وام دیگه در دسترس نیست."


# ---------------------------------------------------------------------------
# جریمه‌ها (برای اطلاع‌رسانی در گروه/PV)
# ---------------------------------------------------------------------------


def penalty_notice(kind: str, detail: int) -> str:
    if kind == "noor":
        return f"⚠️ چون بدهیت رو سر وقت پرداخت نکردی، {_n(detail)} نور ازت کم شد."
    if kind == "toman":
        return f"⚠️ چون بدهیت رو سر وقت پرداخت نکردی، {_money(detail)} از حسابت کم شد."
    return f"🚫 چون بدهیت رو سر وقت پرداخت نکردی، {_n(detail)} ساعت به زندان افتادی."


def insufficient_funds(missing: int) -> str:
    return f"💰 موجودی کافی نیست. {_money(missing)} کم داری."
