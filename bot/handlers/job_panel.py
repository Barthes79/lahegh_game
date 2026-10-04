"""
هندلر پنل «شغل» و «مارکت» (Level 3).

مثل پنل تسبیح/بانک اذکار: هر بار کاربر «شغل» یا «مارکت» بفرستد یک پنل جدید و مستقل ساخته
می‌شود، owner_id داخل callback_data است و کلیک بقیه‌ی کاربران کاملاً بی‌پاسخ می‌ماند.
همه‌ی صفحه‌ها با ویرایش همان یک پیام نمایش داده می‌شوند.

callback_data:  job:<action>:<owner_id>[:<arg>[:<arg2>]]
  main | choose | pick:<job> | pick_ok:<job> | tool_ask | tool_ok
  prod | prod_go:<product> | wh   (فروشگاه در store_panel.py با پیشوند st:)
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update

from bot.database.engine import async_session_factory
from bot.database.models import User
from bot.domain import jobs_data as jd
from bot.services import job_service as js
from bot.services.idempotency import try_claim_update
from bot.services.job_service import JobResult
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id
from bot.texts import job_texts as jt

logger = logging.getLogger(__name__)

router = Router(name="job_panel")

PAGE_MAIN = "main"
PAGE_WAREHOUSE = "warehouse"


# ---------------------------------------------------------------------------
# کیبوردها
# ---------------------------------------------------------------------------


def _btn(text: str, owner_id: int, action: str, *args: str) -> InlineKeyboardButton:
    data = ":".join(["job", action, str(owner_id), *args])
    return InlineKeyboardButton(text=text, callback_data=data)


def _back_row(owner_id: int, action: str = PAGE_MAIN, label: str = "🔙 بازگشت") -> list[InlineKeyboardButton]:
    return [_btn(label, owner_id, action)]


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# ساخت صفحه‌ها (متن + کیبورد)
# ---------------------------------------------------------------------------


async def _inventory_view(session, user: User) -> list[tuple[jd.ProductDef, int, int]]:
    items = await js.get_inventory(session, user)
    return [(jd.PRODUCT_BY_KEY[i.product_key], i.stars, i.quantity) for i in items if i.product_key in jd.PRODUCT_BY_KEY]


async def build_main_page(session, user: User) -> tuple[str, InlineKeyboardMarkup]:
    owner_id = user.telegram_id
    if user.job_key is None:
        return jt.job_choose_page(user.noor_current), _kb(
            [[_btn(f"{j.emoji} {j.name}", owner_id, "pick", j.key)] for j in jd.JOBS]
        )

    job = jd.JOB_BY_KEY[user.job_key]
    prod_row = await js.get_active_production(session, user)
    production = None
    if prod_row is not None:
        production = (jd.PRODUCT_BY_KEY[prod_row.product_key], prod_row.dhikr_done, prod_row.dhikr_required)

    text = jt.job_main_page(
        job=job,
        user_level=user.level,
        tool_level=user.tool_level,
        noor_current=user.noor_current,
        toman=user.toman,
        raw_stock=await js.get_raw_stock(session, user),
        production=production,
        inventory=await _inventory_view(session, user),
    )
    rows = []
    if production is None:
        rows.append([_btn("▶️ شروع تولید", owner_id, "prod")])
    rows.append(
        [
            _btn("📦 انبار", owner_id, "wh"),
            InlineKeyboardButton(text="🏬 فروشگاه", callback_data=f"st:home:{owner_id}"),
        ]
    )
    if user.tool_level < jd.max_tool_level_for_user_level(user.level):
        rows.append([_btn(f"🔧 ارتقای {job.tool_name}", owner_id, "tool_ask")])
    return text, _kb(rows)


async def build_warehouse_page(session, user: User) -> tuple[str, InlineKeyboardMarkup]:
    owner_id = user.telegram_id
    job = jd.JOB_BY_KEY[user.job_key]
    inventory = await _inventory_view(session, user)
    sell_total = sum(jd.get_sell_price(p, s) * q for p, s, q in inventory)
    text = jt.warehouse_page(
        job, user.level, user.toman, await js.get_raw_stock(session, user), inventory, sell_total
    )
    rows = [[InlineKeyboardButton(text="🏬 فروشگاه", callback_data=f"st:home:{owner_id}")]]
    rows.append(_back_row(owner_id))
    return text, _kb(rows)


async def _render(session, user: User, page: str) -> tuple[str, InlineKeyboardMarkup]:
    if page == PAGE_WAREHOUSE and user.job_key is not None:
        return await build_warehouse_page(session, user)
    return await build_main_page(session, user)


def _has_access(user: User) -> bool:
    """سطح ۳ به بالا، یا کسی که قبلاً شغل انتخاب کرده (مثلاً بعد از ریست سطح با کد تست)."""
    return user.level >= jd.JOB_UNLOCK_LEVEL or user.job_key is not None


# ---------------------------------------------------------------------------
# دستورات متنی («شغل» / «مارکت»)
# ---------------------------------------------------------------------------


async def _open_panel(message: Message, page: str) -> None:
    if message.from_user is None:
        return
    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        # قابلیت هنوز باز نشده -> نادیده بگیر (مثل بقیه‌ی قابلیت‌های قفل)
        if user is None or not _has_access(user):
            return
        if page == PAGE_WAREHOUSE and user.job_key is None:
            await message.reply(jt.NO_JOB_YET)
            return
        text, kb = await _render(session, user, page)
    await message.reply(text, reply_markup=kb)


async def show_job_panel(message: Message) -> None:
    await _open_panel(message, PAGE_MAIN)


async def show_warehouse_panel(message: Message) -> None:
    await _open_panel(message, PAGE_WAREHOUSE)


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


@router.callback_query(lambda c: c.data and c.data.startswith("job:"))
async def on_job_callback(callback: CallbackQuery, event_update: Update) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return

    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
        return
    action, owner_id, args = parts[1], int(parts[2]), parts[3:]

    # فقط صاحب پنل — کلیک بقیه کاملاً بدون پاسخ
    if callback.from_user.id != owner_id:
        return

    async with async_session_factory() as session:
        async with session.begin():
            # هر callback فقط یک‌بار پردازش می‌شود (double click / retry)
            if not await try_claim_update(session, event_update.update_id):
                await callback.answer()
                return

            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )
            if not _has_access(user):
                await callback.answer()
                return

            toast: str | None = None
            page = PAGE_MAIN
            text: str | None = None
            kb: InlineKeyboardMarkup | None = None

            if action == "main":
                pass

            elif action == "pick" and user.job_key is None and args and args[0] in jd.JOB_BY_KEY:
                job = jd.JOB_BY_KEY[args[0]]
                text = jt.job_confirm_page(job)
                kb = _kb(
                    [
                        [
                            _btn("تایید ✅", owner_id, "pick_ok", job.key),
                            _btn("انصراف ❌", owner_id, "main"),
                        ]
                    ]
                )

            elif action == "pick_ok" and args:
                out = await js.choose_job(session, user, args[0])
                if out.result == JobResult.SUCCESS:
                    toast = "✅"
                    text_pre = jt.job_chosen(jd.JOB_BY_KEY[args[0]])
                    text, kb = await build_main_page(session, user)
                    text = text_pre + "\n\n" + text
                elif out.result == JobResult.INSUFFICIENT_NOOR:
                    toast = jt.insufficient_noor(out.detail)

            elif action == "tool_ask" and user.job_key is not None:
                cost = jd.get_tool_upgrade_cost(user.tool_level)
                if user.tool_level >= jd.max_tool_level_for_user_level(user.level) or cost is None:
                    toast = jt.TOOL_MAX_FOR_LEVEL
                else:
                    job = jd.JOB_BY_KEY[user.job_key]
                    text = jt.tool_upgrade_confirm(job, user.tool_level, cost)
                    kb = _kb(
                        [[_btn("تایید ✅", owner_id, "tool_ok"), _btn("انصراف ❌", owner_id, "main")]]
                    )

            elif action == "tool_ok" and user.job_key is not None:
                out = await js.upgrade_tool(session, user)
                job = jd.JOB_BY_KEY[user.job_key]
                if out.result == JobResult.SUCCESS:
                    text = jt.tool_upgrade_success(job, out.detail)
                    kb = _kb([_back_row(owner_id)])
                elif out.result == JobResult.INSUFFICIENT_NOOR:
                    toast = jt.insufficient_noor(out.detail)
                elif out.result == JobResult.MAX_TOOL_FOR_LEVEL:
                    toast = jt.TOOL_MAX_FOR_LEVEL

            elif action == "prod" and user.job_key is not None:
                if await js.get_active_production(session, user) is not None:
                    toast = jt.ALREADY_PRODUCING
                else:
                    job = jd.JOB_BY_KEY[user.job_key]
                    stock = await js.get_raw_stock(session, user)
                    text = jt.produce_choose_page(job, user.level, stock)
                    rows = [
                        [_btn(f"{p.emoji} {p.name}", owner_id, "prod_go", p.key)]
                        for p in jd.unlocked_products(job, user.level)
                    ]
                    rows.append(_back_row(owner_id))
                    kb = _kb(rows)

            elif action == "prod_go" and user.job_key is not None and args:
                out = await js.start_production(session, user, args[0])
                if out.result == JobResult.SUCCESS:
                    job = jd.JOB_BY_KEY[user.job_key]
                    text = jt.production_started(job, jd.PRODUCT_BY_KEY[args[0]])
                    kb = _kb([_back_row(owner_id)])
                elif out.result == JobResult.NO_RAW_MATERIAL:
                    toast = jt.NO_RAW_MATERIAL
                elif out.result == JobResult.ALREADY_PRODUCING:
                    toast = jt.ALREADY_PRODUCING

            elif action == "wh" and user.job_key is not None:
                page = PAGE_WAREHOUSE

            if text is None:
                text, kb = await _render(session, user, page)

    await callback.answer(toast, show_alert=bool(toast) and len(toast) > 60)
    await _edit(callback, text, kb)
