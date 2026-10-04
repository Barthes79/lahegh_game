"""
تست‌های Level 3 (مشاغل). اجرا: python tests/test_level3_jobs.py
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_PATH"] = "/tmp/test_laahiq_level3.db"
os.environ.setdefault("BOT_TOKEN", "dummy:token")

DB_PATH = os.environ["DATABASE_PATH"]
for suffix in ("", "-wal", "-shm"):
    if os.path.exists(DB_PATH + suffix):
        os.remove(DB_PATH + suffix)

from bot.database.engine import async_session_factory, run_migrations  # noqa: E402
from bot.domain import jobs_data as jd  # noqa: E402
from bot.domain.salawat_data import LEVEL_3_REQUIRED_SALAWAT  # noqa: E402
from bot.services import job_service as js  # noqa: E402
from bot.services.activity_service import OutcomeStatus, process_activity  # noqa: E402
from bot.services.job_service import JobResult  # noqa: E402
from bot.services.user_service import get_or_create_user  # noqa: E402

SALAWAT = "اللهم صل علی محمد و آل محمد"
DHIKR = "الحمدلله"
_update_id = 1000
_clock = datetime(2026, 1, 1, tzinfo=timezone.utc)


def check(cond: bool, label: str) -> None:
    print(f"[{'OK  ' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(f"TEST FAILED: {label}")


async def act(tg: int, text: str, *, chat: int = -100):
    """یک فعالیت در گروه؛ ساعت هر بار ۱ دقیقه جلو می‌رود تا cooldownها مانع نشوند."""
    global _update_id, _clock
    _update_id += 1
    _clock += timedelta(minutes=1)
    async with async_session_factory() as session:
        async with session.begin():
            return await process_activity(
                session,
                update_id=_update_id,
                telegram_id=tg,
                username=f"u{tg}",
                first_name=f"U{tg}",
                chat_id=chat,
                raw_text=text,
                now=_clock,
            )


async def with_user(tg: int, fn):
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(session, tg, f"u{tg}", f"U{tg}")
            return await fn(session, user)


async def main() -> None:
    await run_migrations()

    print("\n== جدول‌های شانس کیفیت ==")
    for lvl, table in jd.QUALITY_CHANCES.items():
        check(sum(table.values()) == 100, f"مجموع شانس‌های سطح ابزار {lvl} برابر ۱۰۰ است")
    check(set(jd.QUALITY_CHANCES[1]) == {1}, "سطح ۱ ابزار: فقط یک‌ستاره")
    check(len(jd.JOBS) == 5 and all(len(j.products) == 4 for j in jd.JOBS), "۵ شغل × ۴ محصول")
    check(
        all([p.unlock_level for p in j.products] == [3, 4, 5, 6] for j in jd.JOBS),
        "محصولات هر شغل در سطح ۳/۴/۵/۶ باز می‌شوند",
    )
    rng = random.Random(1)
    counts = {s: 0 for s in range(1, 6)}
    for _ in range(20000):
        counts[jd.roll_quality(5, rng)] += 1
    check(abs(counts[5] / 20000 - 0.25) < 0.02 and abs(counts[3] / 20000 - 0.35) < 0.02, "توزیع تصادفی سطح ۵ نزدیک جدول است")
    check(all(jd.roll_quality(1, rng) == 1 for _ in range(200)), "سطح ۱ همیشه یک‌ستاره")

    print("\n== ورود از سطح ۲ به سطح ۳ ==")
    U = 5001
    # ۱۲ صلوات سطح ۱ را کامل می‌کند، صلوات ۱۳ وارد سطح ۲ (1/24)
    for _ in range(13):
        out = await act(U, SALAWAT)
    check(out.level_progress == 1 and out.level_progress_total == 24, "صلوات ۱۳: سطح ۲، پیشرفت ۱/۲۴")
    for i in range(2, 25):
        out = await act(U, SALAWAT)
        check(out.milestone_kind is None, f"پیشرفت سطح ۲ {i}/۲۴ هنوز سطح ۳ نیست") if i in (2, 24) else None
    check(out.level_progress == 24, "سطح ۲ به ۲۴/۲۴ رسید")
    u = await with_user(U, lambda s, user: _ret(user.level))
    check(u == 2, "در ۲۴/۲۴ هنوز سطح ۲ است")
    out = await act(U, SALAWAT)
    check(out.level_up_triggered and out.milestone_kind == "level_up_3", "صلوات بعد از ۲۴/۲۴ -> milestone سطح ۳")
    check(out.level_progress == 1 and out.level_progress_total == LEVEL_3_REQUIRED_SALAWAT, "پیشرفت سطح ۳ از ۱ شروع می‌شود")
    lvl = await with_user(U, lambda s, user: _ret(user.level))
    check(lvl == 3, "level کاربر ۳ شد")
    out = await act(U, SALAWAT)
    check(out.level_progress == 2 and not out.level_up_triggered, "صلوات بعدی: پیشرفت سطح ۳ = ۲")

    print("\n== انتخاب شغل ==")
    async def _low(s, user):
        user.level = 2
        return await js.choose_job(s, user, "farmer")
    low = await with_user(6001, _low)
    check(low.result == JobResult.LEVEL_TOO_LOW, "زیر سطح ۳ نمی‌شود شغل انتخاب کرد")

    async def _setup(s, user):
        user.level = 3
        user.noor_current = 600
        user.noor_total_earned = 600
        return None
    await with_user(U, _setup)
    async def _bad(s, user):
        return await js.choose_job(s, user, "nope")
    check((await with_user(U, _bad)).result == JobResult.INVALID, "شغل نامعتبر رد می‌شود")
    async def _poor(s, user):
        user.noor_current = 100
        r = await js.choose_job(s, user, "farmer")
        user.noor_current = 600
        return r
    check((await with_user(U, _poor)).result == JobResult.INSUFFICIENT_NOOR, "نور ناکافی برای انتخاب شغل")

    async def _choose(s, user):
        r = await js.choose_job(s, user, "farmer")
        return r, user.noor_current, user.noor_total_earned, user.tool_level, user.toman
    r, noor, total, tool, toman = await with_user(U, _choose)
    check(r.result == JobResult.SUCCESS, "انتخاب شغل کشاورز موفق")
    check(noor == 600 - jd.JOB_SELECT_COST_NOOR and total == 600, "نور کم شد ولی noor_total_earned دست‌نخورده")
    check(tool == 1 and toman == jd.STARTING_TOMAN, "ابزار سطح ۱ و تومان اولیه داده شد")
    async def _again(s, user):
        return await js.choose_job(s, user, "attar")
    check((await with_user(U, _again)).result == JobResult.ALREADY_HAS_JOB, "شغل دوم انتخاب نمی‌شود")

    print("\n== ارتقای ابزار (هر سطح یک بار) ==")
    async def _up_poor(s, user):
        user.noor_current = 0
        return await js.upgrade_tool(s, user)
    check((await with_user(U, _up_poor)).result == JobResult.INSUFFICIENT_NOOR, "ارتقا با نور ناکافی رد می‌شود")
    async def _up(s, user):
        user.noor_current = 5000
        r1 = await js.upgrade_tool(s, user)
        r2 = await js.upgrade_tool(s, user)
        return r1, r2, user.tool_level, user.noor_current
    r1, r2, tl, noor = await with_user(U, _up)
    check(r1.result == JobResult.SUCCESS and tl == 2, "در سطح ۳ ابزار از ۱ به ۲ می‌رسد")
    check(r2.result == JobResult.MAX_TOOL_FOR_LEVEL, "در سطح ۳ ارتقای دوم مجاز نیست")
    check(noor == 5000 - jd.TOOL_UPGRADE_COST_NOOR[1], "هزینه‌ی ارتقا کم شد")
    check(jd.max_tool_level_for_user_level(4) == 3 and jd.max_tool_level_for_user_level(6) == 5, "سقف ابزار در سطح ۴ و ۶ درست است")

    print("\n== مارکت، تولید و ذکر ==")
    async def _locked(s, user):
        return await js.buy_raw_material(s, user, "farmer_greens", 1)
    check((await with_user(U, _locked)).result == JobResult.PRODUCT_LOCKED, "سبزی (سطح ۴) در سطح ۳ قفل است")
    async def _other(s, user):
        return await js.buy_raw_material(s, user, "attar_salt", 1)
    check((await with_user(U, _other)).result == JobResult.INVALID, "محصول شغل دیگر قابل خرید نیست")
    async def _noraw(s, user):
        return await js.start_production(s, user, "farmer_potato")
    check((await with_user(U, _noraw)).result == JobResult.NO_RAW_MATERIAL, "بدون ماده‌ی اولیه تولید شروع نمی‌شود")

    async def _buy(s, user):
        before = user.toman
        r = await js.buy_raw_material(s, user, "farmer_potato", 2)
        return r, before - user.toman
    r, spent = await with_user(U, _buy)
    check(r.result == JobResult.SUCCESS and spent == 2 * 1000, "خرید ۲ بذر سیب‌زمینی با تومان")
    async def _broke(s, user):
        user.toman = 10
        r = await js.buy_raw_material(s, user, "farmer_potato", 1)
        user.toman = 5000
        return r
    check((await with_user(U, _broke)).result == JobResult.INSUFFICIENT_TOMAN, "تومان ناکافی برای خرید")

    async def _start(s, user):
        r1 = await js.start_production(s, user, "farmer_potato")
        r2 = await js.start_production(s, user, "farmer_potato")
        stock = await js.get_raw_stock(s, user)
        return r1, r2, stock
    r1, r2, stock = await with_user(U, _start)
    check(r1.result == JobResult.SUCCESS and stock.get("farmer_potato") == 1, "شروع تولید یک بذر مصرف می‌کند")
    check(r2.result == JobResult.ALREADY_PRODUCING, "دو تولید هم‌زمان مجاز نیست")

    for i in range(1, jd.DHIKR_PER_BATCH + 1):
        out = await act(U, DHIKR)
        check(out.status == OutcomeStatus.SUCCESS and out.production is not None, f"ذکر {i}: روی تولید اعمال شد")
        check(out.production.done == i, f"پیشرفت تولید {i}/{jd.DHIKR_PER_BATCH}")
    check(out.production.completed, "با ذکر پنجم تولید کامل شد")
    check(sum(out.production.produced.values()) == jd.TOOL_YIELD_BY_LEVEL[2], "تعداد محصول برابر سطح ابزار (۲)")
    check(set(out.production.produced) <= {1, 2}, "ابزار سطح ۲ فقط ۱ یا ۲ ستاره می‌دهد")
    out = await act(U, DHIKR)
    check(out.production is None, "بعد از پایان تولید، ذکر عادی بدون اثر بر تولید است")

    async def _inv(s, user):
        return [(i.stars, i.quantity) for i in await js.get_inventory(s, user)]
    inv = await with_user(U, _inv)
    check(sum(q for _, q in inv) == 2, "دو محصول در انبار است")

    print("\n== فروشگاه: NPC ==")
    from bot.domain import store_data as sd
    from bot.services import store_service as ss
    from bot.services.store_service import StoreResult

    for k in ("farmer_potato", "attar_saffron"):
        for st in range(1, 6):
            lo, hi = sd.listing_bounds(k, st)
            m = sd.market_price(k, st)
            check(sd.npc_buy_price(k, st) < lo <= m <= hi < sd.npc_sell_price(k, st), f"{k} {st}⭐: NPC ارزان‌تر می‌خرد و گران‌تر می‌فروشد، بازه‌ی آگهی بینشان است")

    async def _npc_sell(s, user):
        before = user.toman
        inv = await js.get_inventory(s, user)
        expected = sum(sd.npc_buy_price(i.product_key, i.stars) * i.quantity for i in inv)
        # همه‌ی ردیف‌ها به NPC
        for i in inv:
            await ss.npc_sell(s, user, i.product_key, i.stars, None)
        r_empty = await ss.npc_sell(s, user, "farmer_potato", 1, None)
        return user.toman - before, expected, r_empty
    gained, expected, r_empty = await with_user(U, _npc_sell)
    check(gained == expected and gained > 0, "فروش به NPC تومان می‌دهد (کمتر از بازار)")
    check(r_empty.result == StoreResult.NOT_ENOUGH_STOCK, "فروش بدون موجودی رد می‌شود")

    async def _npc_buy(s, user):
        user.toman = 10000
        r_poor = await ss.npc_buy(s, user, "attar_saffron", 5, 1)
        r = await ss.npc_buy(s, user, "farmer_potato", 3, 2)
        return r_poor, r, user.toman
    r_poor, r, toman_after = await with_user(U, _npc_buy)
    check(r_poor.result == StoreResult.INSUFFICIENT_TOMAN, "خرید از NPC با تومان ناکافی رد می‌شود")
    check(r.result == StoreResult.SUCCESS and toman_after == 10000 - 2 * sd.npc_sell_price("farmer_potato", 3), "خرید از NPC (گران‌تر از بازار)")

    print("\n== فروشگاه: آگهی کاربران ==")
    S, B = U, 9101  # فروشنده = کاربر U (۲ عدد سیب‌زمینی ۳⭐ دارد)، خریدار = B
    async def _mk_buyer(s, user):
        user.level = 3
        user.toman = 50000
    await with_user(B, _mk_buyer)

    lo, hi = sd.listing_bounds("farmer_potato", 3)
    async def _bad_prices(s, user):
        a = await ss.create_listing(s, user, "farmer_potato", 3, 1, lo - 1)
        b = await ss.create_listing(s, user, "farmer_potato", 3, 1, hi + 1)
        c = await ss.create_listing(s, user, "farmer_potato", 3, 5, lo)  # موجودی کافی نیست
        return a, b, c
    a, b, c = await with_user(S, _bad_prices)
    check(a.result == StoreResult.PRICE_TOO_LOW and a.detail == lo, "قیمت زیر حداقل رد می‌شود")
    check(b.result == StoreResult.PRICE_TOO_HIGH and b.detail == hi, "قیمت بالای حداکثر رد می‌شود")
    check(c.result == StoreResult.NOT_ENOUGH_STOCK, "آگهی بیش از موجودی رد می‌شود")

    async def _list_ok(s, user):
        price = (lo + hi) // 2
        r = await ss.create_listing(s, user, "farmer_potato", 3, 2, price)
        inv = {(i.product_key, i.stars): i.quantity for i in await js.get_inventory(s, user)}
        return r, price, inv.get(("farmer_potato", 3), 0)
    r, price, left = await with_user(S, _list_ok)
    check(r.result == StoreResult.SUCCESS and left == 0, "ثبت آگهی با قیمت دلخواه؛ کالا از انبار فروشنده کم شد (escrow)")

    async def _own(s, user):
        lst = await ss.get_my_listings(s, user)
        return (await ss.buy_listing(s, user, lst[0].id, 1)).result, lst[0].id
    own_res, lid = await with_user(S, _own)
    check(own_res == StoreResult.OWN_LISTING, "خرید از آگهی خود ممنوع است")

    async def _buy(s, user):
        before_b = user.toman
        r1 = await ss.buy_listing(s, user, lid, 1)
        seller = await get_or_create_user(s, S, f"u{S}", f"U{S}")
        return r1, before_b - user.toman, seller.telegram_id
    seller_before = await with_user(S, lambda s, u: _ret(u.toman))
    r1, spent, seller_tg = await with_user(B, _buy)
    check(r1.result == StoreResult.SUCCESS and spent == price and r1.seller_telegram_id == S, "خریدار از آگهی می‌خرد و تومان از او کم می‌شود")
    seller_after = await with_user(S, lambda s, u: _ret(u.toman))
    check(seller_after - seller_before == price, "تومان به فروشنده رسید")
    inv_b = await with_user(B, _inv)
    check(inv_b == [(3, 1)], "کالا به انبار خریدار اضافه شد")

    async def _poor_buy(s, user):
        user.toman = 1
        r = await ss.buy_listing(s, user, lid, 1)
        user.toman = 50000
        return r
    check((await with_user(B, _poor_buy)).result == StoreResult.INSUFFICIENT_TOMAN, "خرید از آگهی با تومان ناکافی رد می‌شود")

    async def _cancel(s, user):
        wrong = await ss.cancel_listing(s, user, lid)
        return wrong.result
    check(await with_user(B, _cancel) == StoreResult.NOT_OWNER, "فقط صاحب آگهی می‌تواند لغو کند")
    async def _cancel_ok(s, user):
        r = await ss.cancel_listing(s, user, lid)
        inv = {(i.product_key, i.stars): i.quantity for i in await js.get_inventory(s, user)}
        gone = await ss.buy_listing(s, user, lid, 1)
        return r.result, inv.get(("farmer_potato", 3), 0), gone.result
    res, back, gone = await with_user(S, _cancel_ok)
    check(res == StoreResult.SUCCESS and back == 1, "لغو آگهی: موجودیِ باقی‌مانده به انبار برگشت")
    check(gone == StoreResult.LISTING_NOT_FOUND, "آگهی لغوشده دیگر وجود ندارد")

    print("\n== فروشگاه: ورود قیمت با ریپلای ==")
    from bot.handlers.store_panel import parse_price
    check(parse_price("۲٬۵۰۰ تومان") == 2500 and parse_price("2,500") == 2500 and parse_price("۳۲۰۰") == 3200, "پارس عدد فارسی/کاما/تومان")
    check(parse_price("abc") is None and parse_price("") is None and parse_price("12a") is None, "متن غیرعددی رد می‌شود")

    async def _prompt(s, user):
        r = await ss.set_price_prompt(s, user, "farmer_potato", 3, 1, -100, 55)
        p = await ss.get_price_prompt(s, user)
        low = await ss.submit_price_from_prompt(s, user, lo - 5)
        still = await ss.get_price_prompt(s, user)
        ok = await ss.submit_price_from_prompt(s, user, lo)
        gone = await ss.get_price_prompt(s, user)
        return r.result, p is not None, low.result, still is not None, ok.result, gone is None
    res = await with_user(S, _prompt)
    check(res == (StoreResult.SUCCESS, True, StoreResult.PRICE_TOO_LOW, True, StoreResult.SUCCESS, True),
          "قیمت اشتباه: درخواست می‌ماند؛ قیمت درست: آگهی ثبت و درخواست پاک می‌شود")

    print("\n== کاربر بدون شغل ==")
    out = await act(7001, SALAWAT)
    out = await act(7001, DHIKR)
    check(out.status == OutcomeStatus.SUCCESS and out.production is None, "بدون شغل ذکر عادی مثل قبل کار می‌کند")

    print("\n== دوبار زدن «شروع تولید» بدون مصرف بذر اضافه ==")
    from bot.handlers.job_panel import on_job_callback as _job_cb
    from unittest.mock import AsyncMock, MagicMock
    from bot.texts import job_texts as jt

    def _cb(data, user_id, mid=42):
        c = MagicMock()
        c.data = data
        c.from_user.id = user_id
        c.from_user.username = "a"
        c.from_user.first_name = "A"
        c.message.chat.id = -5
        c.message.message_id = mid
        c.message.edit_text = AsyncMock()
        c.answer = AsyncMock()
        return c

    DBL = 9500

    async def _prep_dbl(s, user):
        user.level = 3
        user.noor_current = 5000
        await js.choose_job(s, user, "farmer")
        await js.buy_raw_material(s, user, "farmer_potato", 2)
    await with_user(DBL, _prep_dbl)

    upd_counter = [70000]

    def _upd():
        upd_counter[0] += 1
        return MagicMock(update_id=upd_counter[0])

    c1 = _cb(f"job:prod_go:{DBL}:farmer_potato", DBL)
    await _job_cb(c1, _upd())
    stock_after_first = await with_user(DBL, lambda s, u: js.get_raw_stock(s, u))
    check(stock_after_first.get("farmer_potato") == 1, "بعد از شروع تولید اول، ۱ بذر باقی می‌ماند")

    c2 = _cb(f"job:prod_go:{DBL}:farmer_potato", DBL)
    await _job_cb(c2, _upd())
    stock_after_second = await with_user(DBL, lambda s, u: js.get_raw_stock(s, u))
    check(stock_after_second.get("farmer_potato") == 1, "کلیک دوباره روی «شروع تولید» بذر اضافه مصرف نمی‌کند")
    check(c2.answer.await_args.args[0] == jt.ALREADY_PRODUCING, "کلیک دوم پیام «در حال تولید» می‌دهد")

    c3 = _cb(f"job:prod:{DBL}", DBL)
    await _job_cb(c3, _upd())
    check(c3.answer.await_args.args[0] == jt.ALREADY_PRODUCING, "منوی «شروع تولید» هم وقتی تولید فعاله باز نمی‌شود")

    print("\n== رندر پنل‌ها ==")
    from bot.handlers.job_panel import build_main_page
    from bot.handlers import store_panel as sp

    async def _panels(s, user):
        user.level = 3
        m_text, m_kb = await build_main_page(s, user)
        pages = [
            await sp.page_home(s, user),
            await sp.page_raw(s, user),
            await sp.page_shop(s, user),
            await sp.page_category(s, user, "farmer"),
            await sp.page_product(s, user, "farmer_potato"),
            await sp.page_sell(s, user),
            await sp.page_mine(s, user),
        ]
        user.toman = 99999
        await js.buy_raw_material(s, user, "farmer_potato", 1)
        await js.start_production(s, user, "farmer_potato")
        for _ in range(jd.DHIKR_PER_BATCH):
            await js.apply_production_dhikr(s, user)
        inv = await js.get_inventory(s, user)
        pages.append(await sp.page_item(s, user, inv[0].product_key, inv[0].stars))
        return m_text, m_kb, pages
    m_text, m_kb, pages = await with_user(U, _panels)
    check("کشاورز" in m_text and len(m_kb.inline_keyboard) >= 2, "پنل اصلی شغل رندر می‌شود")
    check(any(b.callback_data.startswith("st:home") for r in m_kb.inline_keyboard for b in r), "پنل شغل دکمه‌ی «فروشگاه» دارد")
    check(len(pages) == 8 and all(t for t, _ in pages), "همه‌ی صفحه‌های فروشگاه رندر می‌شوند")
    check(all(len(b.callback_data.encode()) <= 64 for _, k in pages for r in k.inline_keyboard for b in r), "callback_data همه‌ی دکمه‌ها زیر ۶۴ بایت است")
    from bot.handlers.job_panel import build_warehouse_page

    async def _wh(s, user):
        await js.buy_raw_material(s, user, "farmer_potato", 1)
        await js.start_production(s, user, "farmer_potato")
        for _ in range(jd.DHIKR_PER_BATCH):
            await js.apply_production_dhikr(s, user)
        return await build_warehouse_page(s, user)
    w_text, w_kb = await with_user(U, _wh)
    check("انبار" in w_text and "سیب‌زمینی" in w_text and "×" in w_text, "صفحه‌ی انبار محصولات تولیدشده را نشان می‌دهد")
    check(any(b.callback_data.startswith("st:home") for r in w_kb.inline_keyboard for b in r), "انبار دکمه‌ی رفتن به فروشگاه دارد")
    async def _nojob(s, user):
        return await build_main_page(s, user)
    c_text, c_kb = await with_user(8001, _nojob_lvl3)
    check(len(c_kb.inline_keyboard) == 5, "بدون شغل: ۵ دکمه‌ی انتخاب شغل")

    print("\nALL LEVEL 3 TESTS PASSED ✅")


async def _nojob_lvl3(s, user):
    from bot.handlers.job_panel import build_main_page

    user.level = 3
    return await build_main_page(s, user)


async def _ret(v):
    return v


if __name__ == "__main__":
    asyncio.run(main())
