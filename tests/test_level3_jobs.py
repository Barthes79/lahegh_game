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

    print("\n== فروش ==")
    async def _sell(s, user):
        before = user.toman
        r = await js.sell_all_products(s, user)
        r2 = await js.sell_all_products(s, user)
        return r, r2, user.toman - before
    r, r2, gained = await with_user(U, _sell)
    check(r.result == JobResult.SUCCESS and gained == r.detail and gained >= 2 * 1600, "فروش انبار تومان می‌دهد")
    check(r2.result == JobResult.NOTHING_TO_SELL, "انبار خالی چیزی برای فروش ندارد")

    print("\n== کاربر بدون شغل ==")
    out = await act(7001, SALAWAT)
    out = await act(7001, DHIKR)
    check(out.status == OutcomeStatus.SUCCESS and out.production is None, "بدون شغل ذکر عادی مثل قبل کار می‌کند")

    print("\n== رندر پنل‌ها ==")
    from bot.handlers.job_panel import build_main_page, build_market_page

    async def _panels(s, user):
        user.level = 3
        m_text, m_kb = await build_main_page(s, user)
        k_text, k_kb = await build_market_page(s, user)
        return m_text, m_kb, k_text, k_kb
    m_text, m_kb, k_text, k_kb = await with_user(U, _panels)
    check("کشاورز" in m_text and len(m_kb.inline_keyboard) >= 2, "پنل اصلی شغل رندر می‌شود")
    check("مارکت" in k_text and all(len(b.callback_data.encode()) <= 64 for r in k_kb.inline_keyboard for b in r), "پنل مارکت رندر می‌شود و callback_data زیر ۶۴ بایت است")
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
