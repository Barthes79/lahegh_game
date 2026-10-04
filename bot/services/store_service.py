"""
سرویس فروشگاه: آگهی کاربران (با سقف/کف قیمت)، خرید از آگهی‌ها و معامله با NPC.

مثل job_service، همه‌ی توابع باید داخل یک تراکنش صدا زده شوند. تعداد کالای آگهی هنگام ثبت
از انبار فروشنده کم می‌شود (escrow) و با لغو آگهی برمی‌گردد؛ پس کالا هیچ‌وقت تکراری نمی‌شود.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import MarketListing, MarketPricePrompt, User, UserProduct
from bot.domain import jobs_data as jd
from bot.domain import store_data as sd


class StoreResult:
    SUCCESS = "success"
    INVALID = "invalid"
    NOT_ENOUGH_STOCK = "not_enough_stock"
    PRICE_TOO_LOW = "price_too_low"
    PRICE_TOO_HIGH = "price_too_high"
    TOO_MANY_LISTINGS = "too_many_listings"
    LISTING_NOT_FOUND = "listing_not_found"
    OWN_LISTING = "own_listing"
    INSUFFICIENT_TOMAN = "insufficient_toman"
    NOT_OWNER = "not_owner"
    NO_PROMPT = "no_prompt"


@dataclass
class StoreOutcome:
    result: str
    detail: int = 0  # مبلغ / کمبود / حد مجاز قیمت
    seller_telegram_id: int | None = None  # برای اطلاع‌رسانی به فروشنده بعد از خرید
    product_key: str | None = None
    stars: int = 0
    quantity: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# انبار (کم/زیاد کردن محصول)
# ---------------------------------------------------------------------------


async def _get_stock_row(
    session: AsyncSession, user_id: int, product_key: str, stars: int
) -> UserProduct | None:
    return (
        await session.execute(
            select(UserProduct).where(
                UserProduct.user_id == user_id,
                UserProduct.product_key == product_key,
                UserProduct.stars == stars,
            )
        )
    ).scalar_one_or_none()


async def _add_stock(session: AsyncSession, user_id: int, product_key: str, stars: int, qty: int) -> None:
    row = await _get_stock_row(session, user_id, product_key, stars)
    if row is None:
        session.add(UserProduct(user_id=user_id, product_key=product_key, stars=stars, quantity=qty))
    else:
        row.quantity += qty


def _valid_item(product_key: str, stars: int) -> bool:
    return product_key in jd.PRODUCT_BY_KEY and 1 <= stars <= 5


# ---------------------------------------------------------------------------
# NPC
# ---------------------------------------------------------------------------


async def npc_sell(
    session: AsyncSession, user: User, product_key: str, stars: int, quantity: int | None
) -> StoreOutcome:
    """کاربر به NPC می‌فروشد (کمتر از بازار). quantity=None یعنی همه‌ی موجودی آن ردیف."""
    if not _valid_item(product_key, stars):
        return StoreOutcome(StoreResult.INVALID)
    row = await _get_stock_row(session, user.id, product_key, stars)
    have = row.quantity if row else 0
    qty = have if quantity is None else quantity
    if qty < 1 or have < qty:
        return StoreOutcome(StoreResult.NOT_ENOUGH_STOCK)
    total = sd.npc_buy_price(product_key, stars) * qty
    row.quantity -= qty
    user.toman += total
    await session.flush()
    return StoreOutcome(StoreResult.SUCCESS, total, product_key=product_key, stars=stars, quantity=qty)


async def npc_buy(
    session: AsyncSession, user: User, product_key: str, stars: int, quantity: int = 1
) -> StoreOutcome:
    """کاربر از NPC می‌خرد (بیشتر از بازار). موجودی NPC نامحدود است."""
    if not _valid_item(product_key, stars) or quantity < 1:
        return StoreOutcome(StoreResult.INVALID)
    total = sd.npc_sell_price(product_key, stars) * quantity
    if user.toman < total:
        return StoreOutcome(StoreResult.INSUFFICIENT_TOMAN, total - user.toman)
    user.toman -= total
    await _add_stock(session, user.id, product_key, stars, quantity)
    await session.flush()
    return StoreOutcome(StoreResult.SUCCESS, total)


# ---------------------------------------------------------------------------
# آگهی‌ها
# ---------------------------------------------------------------------------


async def create_listing(
    session: AsyncSession,
    user: User,
    product_key: str,
    stars: int,
    quantity: int,
    unit_price: int,
) -> StoreOutcome:
    if not _valid_item(product_key, stars) or quantity < 1:
        return StoreOutcome(StoreResult.INVALID)

    lo, hi = sd.listing_bounds(product_key, stars)
    if unit_price < lo:
        return StoreOutcome(StoreResult.PRICE_TOO_LOW, lo)
    if unit_price > hi:
        return StoreOutcome(StoreResult.PRICE_TOO_HIGH, hi)

    count = len(list((await session.execute(
        select(MarketListing.id).where(MarketListing.seller_id == user.id)
    )).scalars()))
    if count >= sd.MAX_LISTINGS_PER_USER:
        return StoreOutcome(StoreResult.TOO_MANY_LISTINGS, sd.MAX_LISTINGS_PER_USER)

    row = await _get_stock_row(session, user.id, product_key, stars)
    if row is None or row.quantity < quantity:
        return StoreOutcome(StoreResult.NOT_ENOUGH_STOCK)

    row.quantity -= quantity  # escrow
    session.add(
        MarketListing(
            seller_id=user.id,
            product_key=product_key,
            stars=stars,
            quantity=quantity,
            unit_price=unit_price,
            created_at=_now(),
        )
    )
    await session.flush()
    return StoreOutcome(StoreResult.SUCCESS, unit_price * quantity)


async def cancel_listing(session: AsyncSession, user: User, listing_id: int) -> StoreOutcome:
    listing = await session.get(MarketListing, listing_id)
    if listing is None:
        return StoreOutcome(StoreResult.LISTING_NOT_FOUND)
    if listing.seller_id != user.id:
        return StoreOutcome(StoreResult.NOT_OWNER)
    await _add_stock(session, user.id, listing.product_key, listing.stars, listing.quantity)
    await session.delete(listing)
    await session.flush()
    return StoreOutcome(StoreResult.SUCCESS)


async def buy_listing(
    session: AsyncSession, buyer: User, listing_id: int, quantity: int = 1
) -> StoreOutcome:
    listing = await session.get(MarketListing, listing_id)
    if listing is None or listing.quantity < 1:
        return StoreOutcome(StoreResult.LISTING_NOT_FOUND)
    if listing.seller_id == buyer.id:
        return StoreOutcome(StoreResult.OWN_LISTING)
    if quantity < 1:
        return StoreOutcome(StoreResult.INVALID)
    if listing.quantity < quantity:
        return StoreOutcome(StoreResult.NOT_ENOUGH_STOCK, listing.quantity)

    total = listing.unit_price * quantity
    if buyer.toman < total:
        return StoreOutcome(StoreResult.INSUFFICIENT_TOMAN, total - buyer.toman)

    seller = await session.get(User, listing.seller_id)
    buyer.toman -= total
    if seller is not None:
        seller.toman += total
    await _add_stock(session, buyer.id, listing.product_key, listing.stars, quantity)
    listing.quantity -= quantity
    product_key, stars = listing.product_key, listing.stars
    if listing.quantity <= 0:
        await session.delete(listing)
    await session.flush()
    return StoreOutcome(
        StoreResult.SUCCESS,
        total,
        seller_telegram_id=seller.telegram_id if seller else None,
        product_key=product_key,
        stars=stars,
        quantity=quantity,
    )


async def get_listings_for_product(session: AsyncSession, product_key: str, viewer: User):
    """آگهی‌های فعال یک محصول (ارزان‌ترین اول). [(listing, seller_name)]"""
    rows = await session.execute(
        select(MarketListing, User)
        .join(User, User.id == MarketListing.seller_id)
        .where(MarketListing.product_key == product_key, MarketListing.quantity > 0)
        .order_by(MarketListing.unit_price, MarketListing.id)
        .limit(sd.LISTINGS_SHOWN_PER_PRODUCT)
    )
    return [(l, (u.first_name or u.username or "کاربر")) for l, u in rows.all()]


async def count_listings_by_product(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(
        select(MarketListing.product_key, MarketListing.quantity).where(MarketListing.quantity > 0)
    )
    out: dict[str, int] = {}
    for key, qty in rows.all():
        out[key] = out.get(key, 0) + qty
    return out


async def get_my_listings(session: AsyncSession, user: User) -> list[MarketListing]:
    rows = await session.execute(
        select(MarketListing).where(MarketListing.seller_id == user.id).order_by(MarketListing.id)
    )
    return list(rows.scalars())


# ---------------------------------------------------------------------------
# ورود قیمت دلخواه با ریپلای
# ---------------------------------------------------------------------------


async def set_price_prompt(
    session: AsyncSession,
    user: User,
    product_key: str,
    stars: int,
    quantity: int,
    chat_id: int,
    message_id: int,
) -> StoreOutcome:
    if not _valid_item(product_key, stars) or quantity < 1:
        return StoreOutcome(StoreResult.INVALID)
    row = await _get_stock_row(session, user.id, product_key, stars)
    if row is None or row.quantity < quantity:
        return StoreOutcome(StoreResult.NOT_ENOUGH_STOCK)
    await session.execute(delete(MarketPricePrompt).where(MarketPricePrompt.user_id == user.id))
    session.add(
        MarketPricePrompt(
            user_id=user.id,
            product_key=product_key,
            stars=stars,
            quantity=quantity,
            chat_id=chat_id,
            message_id=message_id,
            created_at=_now(),
        )
    )
    await session.flush()
    return StoreOutcome(StoreResult.SUCCESS)


async def get_price_prompt(session: AsyncSession, user: User) -> MarketPricePrompt | None:
    prompt = (
        await session.execute(select(MarketPricePrompt).where(MarketPricePrompt.user_id == user.id))
    ).scalar_one_or_none()
    if prompt is None:
        return None
    created = prompt.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if _now() - created > timedelta(minutes=sd.PRICE_PROMPT_TTL_MINUTES):
        await session.delete(prompt)
        await session.flush()
        return None
    return prompt


async def clear_price_prompt(session: AsyncSession, user: User) -> None:
    await session.execute(delete(MarketPricePrompt).where(MarketPricePrompt.user_id == user.id))
    await session.flush()


async def submit_price_from_prompt(session: AsyncSession, user: User, unit_price: int) -> StoreOutcome:
    """قیمت نوشته‌شده را برای درخواست فعال ثبت می‌کند. در خطای قیمت، درخواست باقی می‌ماند."""
    prompt = await get_price_prompt(session, user)
    if prompt is None:
        return StoreOutcome(StoreResult.NO_PROMPT)
    out = await create_listing(
        session, user, prompt.product_key, prompt.stars, prompt.quantity, unit_price
    )
    if out.result in (StoreResult.SUCCESS, StoreResult.NOT_ENOUGH_STOCK, StoreResult.TOO_MANY_LISTINGS):
        await clear_price_prompt(session, user)
    return out
