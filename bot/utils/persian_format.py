"""
ابزارهای نمایش: تبدیل اعداد به فارسی و رسم نوار پیشرفت.
"""
from __future__ import annotations

_EN_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(value: int | str) -> str:
    return str(value).translate(_EN_TO_FA)


def _progress_bar_chars(current: int, total: int, length: int = 12) -> str:
    total = max(total, 1)
    filled = min(length, round((current / total) * length))
    filled = max(0, min(length, filled))
    return "▰" * filled + "▱" * (length - filled)


def render_progress_bar(current: int, total: int, length: int = 12) -> str:
    """
    نوار پیشرفت مثل: ▰▰▰▰▰▱▱▱▱▱▱▱ ۵ از ۱۲
    length = تعداد کل بلوک‌های نوار (طبق مثال سند، ۱۲ بلوک برای Level 1).
    """
    bar = _progress_bar_chars(current, total, length)
    return f"{bar} {to_persian_digits(current)} از {to_persian_digits(total)}"


def render_progress_bar_bold(current: int, total: int, length: int = 12) -> str:
    """مثل render_progress_bar ولی بخش عددی با ** (Markdown bold) احاطه شده."""
    bar = _progress_bar_chars(current, total, length)
    return f"{bar} **{to_persian_digits(current)} از {to_persian_digits(total)}**"


def format_mmss(total_seconds: int) -> str:
    """قالب M:SS حتی زیر یک دقیقه (مثل 0:42)."""
    total_seconds = max(0, int(total_seconds))
    minutes, seconds = divmod(total_seconds, 60)
    return to_persian_digits(f"{minutes}:{seconds:02d}")
