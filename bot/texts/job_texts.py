"""
متن‌های نمایشی Level 3 (مشاغل، ابزار). متن‌های پنل‌ها با HTML (parse_mode پیش‌فرض ربات)
ساخته می‌شوند؛ فقط پیام ورود به سطح ۳ مثل بقیه‌ی milestoneها با Markdown ارسال می‌شود.
"""
from __future__ import annotations

from bot.domain import jobs_data as jd
from bot.domain.jobs_data import JobDef, ProductDef
from bot.utils.persian_format import render_progress_bar, to_persian_digits


def _n(value: int) -> str:
    return to_persian_digits(value)


def _money(value: int) -> str:
    return to_persian_digits(f"{value:,}").replace(",", "،") + " تومان"


def _stars(stars: int) -> str:
    return "⭐" * stars


# ---------------------------------------------------------------------------
# ورود به سطح ۳ (milestone)
# ---------------------------------------------------------------------------


def level_up_3_message(noor_reward: int, noor_current: int, level_progress: int, level_total: int) -> str:
    return "\n".join(
        [
            "🤲 صلواتت ثبت شد 📿",
            f"✨ +{_n(noor_reward)} نور",
            f"💫 نور معنویتت: {_n(noor_current)}",
            render_progress_bar(level_progress, level_total),
            "",
            "🌟 **مسیر سطح ۲ رو کامل کردی...**",
            "🎉 **تبریک! وارد سطح ۳ شدی.**",
            "",
            "🛠 **یک بخش تازه برات باز شد: مشاغل**",
            "می‌تونی یکی از ۵ شغل رو انتخاب کنی: کشاورز، دامدار، بقال، عطار یا یک‌بارمصرف‌فروش.",
            "برای دیدنش بنویس: **«شغل»**",
        ]
    )


# ---------------------------------------------------------------------------
# انتخاب شغل
# ---------------------------------------------------------------------------

LEVEL_TOO_LOW_NOTE = "این بخش از سطح ۳ باز می‌شود."


def job_choose_page(noor_current: int) -> str:
    lines = [
        "🛠 <b>انتخاب شغل</b>",
        "",
        "یکی از شغل‌ها رو انتخاب کن. هر شغل ۴ محصول داره که به‌ترتیب در سطح ۳ تا ۶ باز می‌شن.",
        f"⚠️ انتخاب شغل <b>{_n(jd.JOB_SELECT_COST_NOOR)} نور</b> هزینه داره و بعدش عوض نمی‌شه.",
        "",
    ]
    for job in jd.JOBS:
        names = "، ".join(p.name for p in job.products)
        lines.append(f"{job.emoji} <b>{job.name}</b> — {names}")
    lines += ["", f"💫 نور معنویتت: {_n(noor_current)}"]
    return "\n".join(lines)


def job_confirm_page(job: JobDef) -> str:
    return "\n".join(
        [
            f"{job.emoji} <b>شغل {job.name}</b>",
            "",
            f"🔧 ابزار: {job.tool_name}",
            f"🧺 ماده‌ی اولیه: {job.raw_name} (از {job.supplier})",
            f"📦 محصول‌ها: {'، '.join(p.name for p in job.products)}",
            "",
            f"💫 هزینه: {_n(jd.JOB_SELECT_COST_NOOR)} نور",
            f"💰 هدیه‌ی شروع: {_money(jd.STARTING_TOMAN)}",
            "",
            "مطمئنی؟",
        ]
    )


def job_chosen(job: JobDef) -> str:
    return (
        f"✅ حالا {job.emoji} <b>{job.name}</b> هستی!\n"
        f"💰 {_money(jd.STARTING_TOMAN)} برای شروع بهت داده شد.\n\n"
        f"اول از «فروشگاه» {job.raw_name} بخر، بعد «شروع تولید» رو بزن و ذکر بگو."
    )


NOT_ENOUGH_NOOR_FOR_JOB = "💫 نورت برای انتخاب این شغل کافی نیست."


def insufficient_noor(missing: int) -> str:
    return f"💫 نورت کافی نیست. {_n(missing)} نور کم داری."


def insufficient_toman(missing: int) -> str:
    return f"💰 تومانت کافی نیست. {_money(missing)} کم داری."


# ---------------------------------------------------------------------------
# صفحه‌ی اصلی شغل
# ---------------------------------------------------------------------------


def _inventory_lines(inventory: list[tuple[ProductDef, int, int]]) -> list[str]:
    if not inventory:
        return ["📦 انبار: خالی"]
    lines = ["📦 <b>انبار</b>"]
    for product, stars, qty in inventory:
        lines.append(f"  {product.emoji} {product.name} {_stars(stars)} × {_n(qty)}")
    return lines


def job_main_page(
    *,
    job: JobDef,
    user_level: int,
    tool_level: int,
    noor_current: int,
    toman: int,
    raw_stock: dict[str, int],
    production: tuple[ProductDef, int, int] | None,
    inventory: list[tuple[ProductDef, int, int]],
) -> str:
    lines = [
        f"{job.emoji} <b>شغل {job.name}</b>",
        "",
        f"🔧 {job.tool_name}: سطح {_n(tool_level)} از {_n(jd.TOOL_MAX_LEVEL)}",
        f"💫 نور: {_n(noor_current)}   💰 {_money(toman)}",
        "",
    ]

    if production is not None:
        product, done, required = production
        lines.append(f"⚙️ در حال تولید {product.emoji} {product.name}")
        lines.append(render_progress_bar(done, required, length=required))
        lines.append(f"ذکر بگو ({_n(required - done)} ذکر دیگه) تا محصول آماده بشه.")
    else:
        lines.append("⚙️ الان تولیدی در جریان نیست.")
    lines.append("")

    lines.append(f"🧺 <b>{job.raw_name}‌های موجود</b>")
    any_raw = False
    for p in jd.unlocked_products(job, user_level):
        qty = raw_stock.get(p.key, 0)
        if qty:
            any_raw = True
            lines.append(f"  {p.emoji} {job.raw_name} {p.name} × {_n(qty)}")
    if not any_raw:
        lines.append("  خالی")
    lines.append("")

    lines += _inventory_lines(inventory)

    locked = [p for p in job.products if p.unlock_level > user_level]
    if locked:
        lines.append("")
        lines.append("🔒 " + "، ".join(f"{p.name} (سطح {_n(p.unlock_level)})" for p in locked))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ابزار
# ---------------------------------------------------------------------------


def _quality_lines(tool_level: int) -> list[str]:
    table = jd.QUALITY_CHANCES.get(tool_level, {})
    return [f"  {_stars(s)}: {_n(pct)}٪" for s, pct in table.items()]


def tool_upgrade_confirm(job: JobDef, tool_level: int, cost: int) -> str:
    nxt = tool_level + 1
    return "\n".join(
        [
            f"🔧 <b>ارتقای {job.tool_name}</b>",
            f"سطح {_n(tool_level)} ← سطح {_n(nxt)}",
            f"💫 هزینه: {_n(cost)} نور",
            f"📦 تعداد هر تولید: {_n(jd.TOOL_YIELD_BY_LEVEL[tool_level])} ← {_n(jd.TOOL_YIELD_BY_LEVEL[nxt])}",
            "",
            f"شانس کیفیت در سطح {_n(nxt)}:",
            *_quality_lines(nxt),
            "",
            "تایید می‌کنی؟",
        ]
    )


def tool_upgrade_success(job: JobDef, new_level: int) -> str:
    return "\n".join(
        [
            f"✅ {job.tool_name} به سطح {_n(new_level)} رسید!",
            f"📦 تعداد هر تولید: {_n(jd.TOOL_YIELD_BY_LEVEL[new_level])}",
            "شانس کیفیت:",
            *_quality_lines(new_level),
        ]
    )


TOOL_MAX_FOR_LEVEL = "🔧 در این سطح یک‌بار ابزارت رو ارتقا دادی؛ با رسیدن به سطح بعد دوباره می‌تونی."


# ---------------------------------------------------------------------------
# تولید
# ---------------------------------------------------------------------------


def produce_choose_page(job: JobDef, user_level: int, raw_stock: dict[str, int]) -> str:
    lines = [f"▶️ <b>شروع تولید</b>", "", "کدوم محصول رو تولید کنیم؟ (هر بار ۱ واحد " + job.raw_name + " مصرف می‌شه)", ""]
    for p in jd.unlocked_products(job, user_level):
        lines.append(f"{p.emoji} {p.name} — {job.raw_name} موجود: {_n(raw_stock.get(p.key, 0))}")
    lines += ["", f"هر تولید {_n(jd.DHIKR_PER_BATCH)} ذکر می‌خواد."]
    return "\n".join(lines)


def production_started(job: JobDef, product: ProductDef) -> str:
    return (
        f"⚙️ تولید {product.emoji} {product.name} شروع شد.\n"
        f"{job.produce_verb}.\n\n"
        f"در گروه {_n(jd.DHIKR_PER_BATCH)} ذکر بگو."
    )


NO_RAW_MATERIAL = "🧺 ماده‌ی اولیه‌ی این محصول رو نداری؛ اول از «فروشگاه» بخر."
ALREADY_PRODUCING = "⚙️ یک تولید در جریانه؛ اول اون رو تموم کن."


def production_progress_pv(product: ProductDef, done: int, required: int) -> str:
    return (
        f"⚙️ تولید {product.emoji} {product.name}\n"
        f"{render_progress_bar(done, required, length=required)}"
    )


def production_complete_group(product: ProductDef, produced: dict[int, int]) -> str:
    parts = [f"{_stars(s)} × {_n(q)}" for s, q in sorted(produced.items())]
    return (
        f"✅ تولید {product.emoji} {product.name} تموم شد!\n"
        f"📦 {'، '.join(parts)} به انبارت اضافه شد.\n"
        "برای دیدن انبار بنویس: «انبار»"
    )


NO_JOB_YET = "اول باید یک شغل انتخاب کنی. بنویس: «شغل»"


# ---------------------------------------------------------------------------
# انبار
# ---------------------------------------------------------------------------


def warehouse_page(
    job: JobDef,
    user_level: int,
    toman: int,
    raw_stock: dict[str, int],
    inventory: list[tuple[ProductDef, int, int]],
    sell_total: int,
) -> str:
    lines = [f"📦 <b>انبار {job.name}</b>", f"💰 {_money(toman)}", "", "🧾 <b>محصولات</b>"]
    if inventory:
        for product, stars, qty in inventory:
            lines.append(
                f"  {product.emoji} {product.name} {_stars(stars)} × {_n(qty)}"
                f" — هرکدام {_money(jd.get_sell_price(product, stars))}"
            )
        lines.append(f"💵 ارزش فروش کل: {_money(sell_total)}")
    else:
        lines.append("  خالی — با «شغل» و «شروع تولید» محصول بساز.")

    lines += ["", f"🧺 <b>{job.raw_name}‌ها</b>"]
    any_raw = False
    for p in jd.unlocked_products(job, user_level):
        qty = raw_stock.get(p.key, 0)
        if qty:
            any_raw = True
            lines.append(f"  {p.emoji} {job.raw_name} {p.name} × {_n(qty)}")
    if not any_raw:
        lines.append("  خالی")
    return "\n".join(lines)
