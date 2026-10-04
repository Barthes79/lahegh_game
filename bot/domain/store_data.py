"""
قوانین خالص فروشگاه (بدون وابستگی به تلگرام/دیتابیس).

«قیمت بازار» هر محصول = قیمت پایه‌ی محصول × ضریب ستاره (jobs_data.get_sell_price).
- آگهی کاربران باید بین حداقل و حداکثر قیمت مجاز باشد.
- NPC از کاربر ارزان‌تر از بازار می‌خرد و گران‌تر از بازار می‌فروشد؛
  پس همیشه «آگهی به کاربر» برای فروشنده و خریدار بهتر از NPC است.

⚠️ [PLACEHOLDER] همه‌ی ضریب‌ها در سند مشخص نبود و فقط همین‌جا تعریف شده‌اند.
"""
from __future__ import annotations

from bot.domain import jobs_data as jd

LISTING_MIN_FACTOR = 0.7  # حداقل قیمت آگهی = ۷۰٪ بازار
LISTING_MAX_FACTOR = 1.3  # حداکثر قیمت آگهی = ۱۳۰٪ بازار
NPC_BUY_FACTOR = 0.5  # NPC از کاربر می‌خرد: ۵۰٪ بازار (کمتر از بازار)
NPC_SELL_FACTOR = 1.5  # NPC به کاربر می‌فروشد: ۱۵۰٪ بازار (بیشتر از بازار)

NPC_NAME = "عمو رحمان"
NPC_EMOJI = "🧔"

MAX_LISTINGS_PER_USER = 10
PRICE_PROMPT_TTL_MINUTES = 30
LISTINGS_SHOWN_PER_PRODUCT = 6


def market_price(product_key: str, stars: int) -> int:
    return jd.get_sell_price(jd.PRODUCT_BY_KEY[product_key], stars)


def listing_bounds(product_key: str, stars: int) -> tuple[int, int]:
    base = market_price(product_key, stars)
    lo = max(1, int(round(base * LISTING_MIN_FACTOR)))
    hi = max(lo, int(round(base * LISTING_MAX_FACTOR)))
    return lo, hi


def npc_buy_price(product_key: str, stars: int) -> int:
    """قیمتی که NPC به کاربر می‌دهد (کاربر می‌فروشد)."""
    return max(1, int(round(market_price(product_key, stars) * NPC_BUY_FACTOR)))


def npc_sell_price(product_key: str, stars: int) -> int:
    """قیمتی که کاربر به NPC می‌دهد (کاربر می‌خرد)."""
    return max(1, int(round(market_price(product_key, stars) * NPC_SELL_FACTOR)))
