"""
هندلر پنل «فروشگاه» (ادغام‌شده با مارکت مواد اولیه).

بخش‌ها: خرید مواد اولیه · خرید از بازار (آگهی کاربران + NPC) · فروش (آگهی با قیمت دلخواه یا
فروش فوری به NPC) · آگهی‌های من.

مثل بقیه‌ی پنل‌ها: هر بار «فروشگاه» ← یک پنل مستقل، owner_id داخل callback_data و کلیک بقیه‌ی
کاربران کاملاً بی‌پاسخ. قیمت دلخواه آگهی با «ریپلای روی پیام پنل» گرفته می‌شود
(try_handle_price_reply از group_messages صدا زده می‌شود).

callback_data:  st:<action>:<owner_id>[:args...]
"""
from __future__ import annotations

import logging
import re

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update

from bot.database.engine import async_session_factory
from bot.database.models import User
from bot.domain import jobs_data as jd
from bot.services import job_service as js
from bot.services import store_service as ss
from bot.services.idempotency import try_claim_update
from bot.services.job_service import JobResult
from bot.services.store_service import StoreResult
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id
from bot.texts import store_texts as tt

logger = logging.getLogger(__name__)

router = Router(name="store_panel")


def _has_access(user: User) -> bool:
    return user.level >= jd.JOB_UNLOCK_LEVEL or user.job_key is not None


def _btn(text: str, owner_id: int, action: str, *args: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=":".join(["st", action, str(owner_id), *args]))


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _home_btn(owner_id: int) -> list[InlineKeyboardButton]:
    return [_btn("🔙 فروشگاه", owner_id, "home")]


def _stars(n: int) -> str:
    return "⭐" * n


# ---------------------------------------------------------------------------
# صفحه‌ها
# ---------------------------------------------------------------------------


async def _inventory_view(session, user: User) -> list[tuple[jd.ProductDef, int, int]]:
    items = await js.get_inventory(session, user)
    return [(jd.PRODUCT_BY_KEY[i.product_key], i.stars, i.quantity) for i in items if i.product_key in jd.PRODUCT_BY_KEY]


async def page_home(session, user: User):
    o = user.telegram_id
    mine = await ss.get_my_listings(session, user)
    rows = []
    if user.job_key is not None:
        rows.append([_btn("🛒 خرید مواد اولیه", o, "raw")])
    rows.append([_btn("👥 خرید از بازار", o, "shop"), _btn("💰 فروش محصولات", o, "sell")])
    rows.append([_btn("📋 آگهی‌های من", o, "mine")])
    if user.job_key is not None:
        rows.append([InlineKeyboardButton(text="🔙 پنل شغل", callback_data=f"job:main:{o}")])
    return tt.store_home(user.toman, user.job_key is not None, len(mine)), _kb(rows)


async def page_raw(session, user: User):
    o = user.telegram_id
    job = jd.JOB_BY_KEY[user.job_key]
    text = tt.raw_page(job, user.level, user.toman, await js.get_raw_stock(session, user))
    rows = [
        [_btn(f"{p.emoji} خرید ۱", o, "rbuy", p.key, "1"), _btn(f"{p.emoji} خرید ۵", o, "rbuy", p.key, "5")]
        for p in jd.unlocked_products(job, user.level)
    ]
    rows.append(_home_btn(o))
    return text, _kb(rows)


async def page_shop(session, user: User):
    o = user.telegram_id
    by_product = await ss.count_listings_by_product(session)
    by_job = {j.key: sum(by_product.get(p.key, 0) for p in j.products) for j in jd.JOBS}
    rows = [[_btn(f"{j.emoji} {j.name}", o, "cat", j.key)] for j in jd.JOBS]
    rows.append(_home_btn(o))
    return tt.shop_categories(by_job), _kb(rows)


async def page_category(session, user: User, job_key: str):
    o = user.telegram_id
    job = jd.JOB_BY_KEY[job_key]
    counts = await ss.count_listings_by_product(session)
    rows = [[_btn(f"{p.emoji} {p.name}", o, "prod", p.key)] for p in job.products]
    rows.append([_btn("🔙 دسته‌ها", o, "shop")])
    return tt.shop_products(job, counts), _kb(rows)


async def page_product(session, user: User, product_key: str):
    o = user.telegram_id
    product = jd.PRODUCT_BY_KEY[product_key]
    listings = await ss.get_listings_for_product(session, product_key, user)
    text = tt.product_page(product, user.toman, listings)
    rows = []
    for l, seller in listings:
        rows.append(
            [_btn(f"🛍 {_stars(l.stars)} ×۱ — {l.unit_price:,} ({seller[:12]})", o, "lbuy", str(l.id))]
        )
    rows.append(
        [_btn(f"🧔 {_stars(s)}", o, "npcbuy", product_key, str(s)) for s in (1, 2, 3)]
    )
    rows.append([_btn(f"🧔 {_stars(s)}", o, "npcbuy", product_key, str(s)) for s in (4, 5)])
    job = jd.JOB_OF_PRODUCT[product_key]
    rows.append([_btn("🔙 " + job.name, o, "cat", job.key)])
    return text, _kb(rows)


async def page_sell(session, user: User):
    o = user.telegram_id
    inv = await _inventory_view(session, user)
    rows = [
        [_btn(f"{p.emoji} {p.name} {_stars(s)} × {q}", o, "item", p.key, str(s))] for p, s, q in inv
    ]
    rows.append(_home_btn(o))
    return tt.sell_page(user.toman, inv), _kb(rows)


async def page_item(session, user: User, product_key: str, stars: int):
    o = user.telegram_id
    product = jd.PRODUCT_BY_KEY[product_key]
    inv = {(p.key, s): q for p, s, q in await _inventory_view(session, user)}
    have = inv.get((product_key, stars), 0)
    if have < 1:
        return await page_sell(session, user)
    rows = [
        [_btn("🧔 فروش ۱ به NPC", o, "npcsell", product_key, str(stars), "1"),
         _btn(f"🧔 فروش همه ({have})", o, "npcsell", product_key, str(stars), "all")],
        [_btn("📝 آگهی ۱ عدد", o, "list", product_key, str(stars), "1"),
         _btn(f"📝 آگهی همه ({have})", o, "list", product_key, str(stars), "all")],
        [_btn("🔙 فروش", o, "sell")],
    ]
    return tt.sell_item_page(product, stars, have), _kb(rows)


async def page_mine(session, user: User):
    o = user.telegram_id
    mine = await ss.get_my_listings(session, user)
    rows = []
    for l in mine:
        p = jd.PRODUCT_BY_KEY.get(l.product_key)
        if p:
            rows.append([_btn(f"❌ لغو {p.name} {_stars(l.stars)} × {l.quantity}", o, "cancel", str(l.id))])
    rows.append(_home_btn(o))
    return tt.my_listings_page(mine), _kb(rows)


# ---------------------------------------------------------------------------
# دستور متنی «فروشگاه»
# ---------------------------------------------------------------------------


async def show_store_panel(message: Message) -> None:
    if message.from_user is None:
        return
    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if user is None or not _has_access(user):
            return  # هنوز باز نشده (مثل بقیه‌ی قابلیت‌های قفل)
        text, kb = await page_home(session, user)
    await message.reply(text, reply_markup=kb)


# ---------------------------------------------------------------------------
# ورود قیمت دلخواه (ریپلای روی پیام پنل)
# ---------------------------------------------------------------------------

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_price(text: str) -> int | None:
    cleaned = text.translate(_DIGITS)
    cleaned = re.sub(r"[,\u060c\u066c\s]|تومان", "", cleaned)
    if not cleaned.isdigit() or len(cleaned) > 9:
        return None
    return int(cleaned)


async def try_handle_price_reply(message: Message, event_update: Update) -> bool:
    """
    اگر پیام ریپلای روی پنلِ «در انتظار قیمت» همین کاربر باشد پردازش می‌شود و True برمی‌گردد
    (دیگر نباید به‌عنوان ذکر/صلوات بررسی شود). در غیر این صورت False و هیچ اثری ندارد.
    """
    if message.reply_to_message is None or message.from_user is None or not message.text:
        return False

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user is None:
                return False
            prompt = await ss.get_price_prompt(session, user)
            if (
                prompt is None
                or prompt.chat_id != message.chat.id
                or prompt.message_id != message.reply_to_message.message_id
            ):
                return False

            if not await try_claim_update(session, event_update.update_id):
                return True

            price = parse_price(message.text)
            if price is None:
                reply = tt.PRICE_NOT_A_NUMBER
            else:
                product_key, stars, qty = prompt.product_key, prompt.stars, prompt.quantity
                out = await ss.submit_price_from_prompt(session, user, price)
                if out.result == StoreResult.SUCCESS:
                    reply = tt.listing_created(jd.PRODUCT_BY_KEY[product_key], stars, qty, price)
                elif out.result == StoreResult.PRICE_TOO_LOW:
                    reply = tt.price_out_of_range(out.detail, True)
                elif out.result == StoreResult.PRICE_TOO_HIGH:
                    reply = tt.price_out_of_range(out.detail, False)
                elif out.result == StoreResult.TOO_MANY_LISTINGS:
                    reply = tt.TOO_MANY_LISTINGS
                else:
                    reply = tt.NOT_ENOUGH_STOCK
    await message.reply(reply)
    return True


# ---------------------------------------------------------------------------
# callbackها
# ---------------------------------------------------------------------------


async def _edit(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        logger.debug("edit_text ignored: %s", exc)


def _valid_item(key: str, stars_s: str) -> int | None:
    if key in jd.PRODUCT_BY_KEY and stars_s.isdigit() and 1 <= int(stars_s) <= 5:
        return int(stars_s)
    return None


@router.callback_query(lambda c: c.data and c.data.startswith("st:"))
async def on_store_callback(callback: CallbackQuery, event_update: Update) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
        return
    action, owner_id, args = parts[1], int(parts[2]), parts[3:]
    if callback.from_user.id != owner_id:
        return  # فقط صاحب پنل

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
            if not _has_access(user):
                await callback.answer()
                return

            page = None  # (text, kb)

            if action == "home":
                await ss.clear_price_prompt(session, user)

            elif action == "raw" and user.job_key is not None:
                page = await page_raw(session, user)

            elif action == "rbuy" and user.job_key is not None and len(args) == 2 and args[1] in ("1", "5"):
                out = await js.buy_raw_material(session, user, args[0], int(args[1]))
                if out.result == JobResult.SUCCESS:
                    toast = tt.raw_bought(jd.JOB_BY_KEY[user.job_key], jd.PRODUCT_BY_KEY[args[0]], int(args[1]), out.detail)
                elif out.result == JobResult.INSUFFICIENT_TOMAN:
                    toast = tt.insufficient_toman(out.detail)
                page = await page_raw(session, user)

            elif action == "shop":
                page = await page_shop(session, user)

            elif action == "cat" and args and args[0] in jd.JOB_BY_KEY:
                page = await page_category(session, user, args[0])

            elif action == "prod" and args and args[0] in jd.PRODUCT_BY_KEY:
                page = await page_product(session, user, args[0])

            elif action == "npcbuy" and len(args) == 2 and _valid_item(*args):
                stars = int(args[1])
                out = await ss.npc_buy(session, user, args[0], stars, 1)
                if out.result == StoreResult.SUCCESS:
                    toast = tt.bought_from_npc(jd.PRODUCT_BY_KEY[args[0]], stars, out.detail)
                elif out.result == StoreResult.INSUFFICIENT_TOMAN:
                    toast = tt.insufficient_toman(out.detail)
                page = await page_product(session, user, args[0])

            elif action == "lbuy" and args and args[0].isdigit():
                out = await ss.buy_listing(session, user, int(args[0]), 1)
                product_key = None
                if out.result == StoreResult.SUCCESS:
                    product_key, stars = out.product_key, out.stars
                    p = jd.PRODUCT_BY_KEY[product_key]
                    toast = tt.bought_listing(p, stars, 1, out.detail)
                    if out.seller_telegram_id:
                        name = callback.from_user.first_name or callback.from_user.username or "یک کاربر"
                        notify = (out.seller_telegram_id, tt.seller_notice(name, p, stars, 1, out.detail))
                elif out.result == StoreResult.INSUFFICIENT_TOMAN:
                    toast = tt.insufficient_toman(out.detail)
                elif out.result == StoreResult.OWN_LISTING:
                    toast = tt.OWN_LISTING
                else:
                    toast = tt.LISTING_GONE
                page = await page_product(session, user, product_key) if product_key else await page_shop(session, user)

            elif action == "sell":
                page = await page_sell(session, user)

            elif action == "item" and len(args) == 2 and _valid_item(*args):
                page = await page_item(session, user, args[0], int(args[1]))

            elif action == "npcsell" and len(args) == 3 and _valid_item(args[0], args[1]) and args[2] in ("1", "all"):
                stars = int(args[1])
                qty = None if args[2] == "all" else 1
                out = await ss.npc_sell(session, user, args[0], stars, qty)
                if out.result == StoreResult.SUCCESS:
                    toast = tt.npc_sold(jd.PRODUCT_BY_KEY[args[0]], stars, out.quantity, out.detail)
                else:
                    toast = tt.NOT_ENOUGH_STOCK
                page = await page_item(session, user, args[0], stars)

            elif action == "list" and len(args) == 3 and _valid_item(args[0], args[1]) and args[2] in ("1", "all"):
                stars = int(args[1])
                inv = {(p.key, s): q for p, s, q in await _inventory_view(session, user)}
                have = inv.get((args[0], stars), 0)
                qty = have if args[2] == "all" else 1
                out = await ss.set_price_prompt(
                    session, user, args[0], stars, qty, callback.message.chat.id, callback.message.message_id
                ) if have >= 1 else None
                if out is not None and out.result == StoreResult.SUCCESS:
                    text = tt.price_prompt_page(jd.PRODUCT_BY_KEY[args[0]], stars, qty)
                    kb = _kb([[_btn("❌ انصراف", owner_id, "home")]])
                    page = (text, kb)
                else:
                    toast = tt.NOT_ENOUGH_STOCK
                    page = await page_sell(session, user)

            elif action == "mine":
                page = await page_mine(session, user)

            elif action == "cancel" and args and args[0].isdigit():
                out = await ss.cancel_listing(session, user, int(args[0]))
                toast = tt.listing_cancelled() if out.result == StoreResult.SUCCESS else tt.LISTING_GONE
                page = await page_mine(session, user)

            if page is None:
                page = await page_home(session, user)
            text, kb = page

    await callback.answer(toast, show_alert=bool(toast) and len(toast) > 60)
    await _edit(callback, text, kb)

    if notify is not None:
        try:
            await callback.bot.send_message(chat_id=notify[0], text=notify[1])
        except Exception:  # noqa: BLE001 — فروشنده ممکن است ربات را استارت نکرده باشد
            logger.debug("اطلاع‌رسانی فروش به فروشنده ناموفق بود", exc_info=True)
