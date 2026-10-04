"""
قوانین خالص بانک (بدون وابستگی به تلگرام/دیتابیس): شماره کارت، قرض‌الحسنه، جریمه‌ی تأخیر.

⚠️ [PLACEHOLDER] همه‌ی عددهای زیر در سند مشخص نبود و فقط همین‌جا تعریف شده‌اند.
"""
from __future__ import annotations

import random

CARD_BIN = "6219"  # پیشوند ساختگی «بانک لاحق»
CARD_DIGITS = 16

LOAN_MIN_AMOUNT = 2_000
LOAN_MAX_AMOUNT = 50_000
# مبلغ بازپرداخت کمی بیشتر از مبلغ وام است؛ این افزوده به کسی که وام داده تعلق می‌گیرد
# (طبق درخواست: «اون پول یه مقدار بیشتر میشه و به کسی که وام داده داده میشه»).
LOAN_REPAY_FACTOR = 1.15
LOAN_DUE_HOURS = 48

# پاداش نورِ کسی که وام می‌دهد، همان لحظه‌ی پرداخت (نه در بازپرداخت).
LOAN_LENDER_NOOR_PER_1000 = 5
LOAN_LENDER_NOOR_MIN = 5

# اگر سررسید (۴۸ ساعت) بگذرد و بدهی پرداخت نشده باشد، هر ۲۴ ساعت یک‌بار یکی از این سه
# جریمه به‌صورت تصادفی روی بدهکار اعمال می‌شود؛ بدهی همچنان باقی می‌ماند.
LOAN_PENALTY_RECHECK_HOURS = 24
LOAN_PENALTY_NOOR_PERCENT = 0.20
LOAN_PENALTY_TOMAN_PERCENT = 0.20
LOAN_PENALTY_JAIL_HOURS = 3

MAX_LOANS_LISTED = 8


def repay_amount_for(amount: int) -> int:
    return max(amount + 1, int(round(amount * LOAN_REPAY_FACTOR)))


def lender_noor_reward_for(amount: int) -> int:
    return max(LOAN_LENDER_NOOR_MIN, int(round(amount / 1000 * LOAN_LENDER_NOOR_PER_1000)))


_CARD_DIGIT_TRANSLATE = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def generate_card_digits() -> str:
    rest = "".join(str(random.randint(0, 9)) for _ in range(CARD_DIGITS - len(CARD_BIN)))
    return CARD_BIN + rest


def format_card_number(digits: str) -> str:
    return "-".join(digits[i : i + 4] for i in range(0, len(digits), 4))


def normalize_card_number(raw: str) -> str | None:
    """ورودی کاربر (با خط‌تیره/فاصله/ارقام فارسی) را به ۱۶ رقم انگلیسی خام تبدیل می‌کند."""
    cleaned = raw.translate(_CARD_DIGIT_TRANSLATE)
    cleaned = "".join(ch for ch in cleaned if ch.isdigit())
    if len(cleaned) != CARD_DIGITS:
        return None
    return cleaned
