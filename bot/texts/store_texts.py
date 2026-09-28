"""متن‌های نمایشی فروشگاه (HTML، مثل بقیه‌ی پنل‌ها)."""
from __future__ import annotations

from bot.domain import jobs_data as jd
from bot.domain import store_data as sd
from bot.domain.jobs_data import JobDef, ProductDef
from bot.utils.persian_format import to_persian_digits


def _n(value: int) -> str:
    return to_persian_digits(value)


def _money(value: int) -> str:
    return to_persian_digits(f"{value:,}").replace(",", "،") + " تومان"


def _stars(stars: int) -> str:
    return "⭐" * stars


NPC = f"{sd.NPC_EMOJI} {sd.NPC_NAME}"


# ---------------------------------------------------------------------------
# صفحه‌ی اصلی
# ---------------------------------------------------------------------------


def store_home(toman: int, has_job: bool, my_listings: int) -> str:
    lines = [
        "🏬 <b>فروشگاه</b>",
        f"💰 {_money(toman)}",
        "",
        "🛒 <b>خرید مواد اولیه</b> — بذر، علوفه و ... برای تولید" if has_job else "🔒 خرید مواد اولیه فقط برای کسانی است که شغل دارند.",
        "👥 <b>خرید از بازار</b> — محصولات بقیه‌ی کاربران و " + NPC,
        "💰 <b>فروش محصولات</b> — آگهی با قیمت دلخواه یا فروش فوری به " + NPC,
        f"📋 <b>آگهی‌های من</b> ({_n(my_listings)})",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# مواد اولیه
# ---------------------------------------------------------------------------


def raw_page(job: JobDef, user_level: int, toman: int, raw_stock: dict[str, int]) -> str:
    lines = [
        f"🛒 <b>خرید {job.raw_name}</b> (از {job.supplier})",
        f"💰 {_money(toman)}",
        "",
    ]
    for p in jd.unlocked_products(job, user_level):
        lines.append(
            f"  {p.emoji} {job.raw_name} {p.name} — {_money(p.raw_price)}"
            f" (موجود: {_n(raw_stock.get(p.key, 0))})"
        )
    return "\n".join(lines)


def raw_bought(job: JobDef, product: ProductDef, quantity: int, total: int) -> str:
    return f"🛒 {_n(quantity)} {job.raw_name} {product.name} خریدی ({_money(total)})."


# ---------------------------------------------------------------------------
# بازار (خرید)
# ---------------------------------------------------------------------------


def shop_categories(counts_by_job: dict[str, int]) -> str:
    lines = [
        "👥 <b>خرید از بازار</b>",
        "",
        "دسته‌ی محصول رو انتخاب کن. آگهی کاربران معمولاً از " + NPC + " ارزون‌تره.",
        "",
    ]
    for job in jd.JOBS:
        lines.append(f"{job.emoji} {job.name} — {_n(counts_by_job.get(job.key, 0))} آگهی")
    return "\n".join(lines)


def shop_products(job: JobDef, counts: dict[str, int]) -> str:
    lines = [f"{job.emoji} <b>محصولات {job.name}</b>", ""]
    for p in job.products:
        lines.append(f"{p.emoji} {p.name} — {_n(counts.get(p.key, 0))} عدد در آگهی‌ها")
    return "\n".join(lines)


def product_page(
    product: ProductDef, toman: int, listings: list[tuple[object, str]]
) -> str:
    lines = [f"{product.emoji} <b>{product.name}</b>", f"💰 {_money(toman)}", ""]
    lines.append("👥 <b>آگهی‌های کاربران</b> (ارزون‌ترین اول)")
    if listings:
        for l, seller in listings:
            lines.append(
                f"  {_stars(l.stars)} × {_n(l.quantity)} — هرکدام {_money(l.unit_price)} — {seller}"
            )
    else:
        lines.append("  آگهی‌ای نیست.")
    lines += ["", f"{NPC} (فروش به تو، گران‌تر از بازار):"]
    for s in range(1, 6):
        lines.append(f"  {_stars(s)} — {_money(sd.npc_sell_price(product.key, s))}")
    return "\n".join(lines)


def bought_listing(product: ProductDef, stars: int, quantity: int, total: int) -> str:
    return f"🛍 {_n(quantity)} {product.name} {_stars(stars)} خریدی ({_money(total)})."


def bought_from_npc(product: ProductDef, stars: int, total: int) -> str:
    return f"{sd.NPC_EMOJI} ۱ {product.name} {_stars(stars)} از {sd.NPC_NAME} خریدی ({_money(total)})."


def seller_notice(buyer_name: str, product: ProductDef, stars: int, quantity: int, total: int) -> str:
    return (
        f"🛍 {buyer_name} تعداد {_n(quantity)} {product.name} {_stars(stars)} از آگهی‌ات خرید.\n"
        f"💰 {_money(total)} به حسابت اضافه شد."
    )


# ---------------------------------------------------------------------------
# فروش
# ---------------------------------------------------------------------------


def sell_page(toman: int, inventory: list[tuple[ProductDef, int, int]]) -> str:
    lines = ["💰 <b>فروش محصولات</b>", f"💰 {_money(toman)}", ""]
    if not inventory:
        lines.append("انبارت خالیه. اول با «شغل» تولید کن.")
    else:
        lines.append("یکی از محصولات انبارت رو انتخاب کن:")
        for p, stars, qty in inventory:
            lines.append(f"  {p.emoji} {p.name} {_stars(stars)} × {_n(qty)}")
    return "\n".join(lines)


def sell_item_page(product: ProductDef, stars: int, have: int) -> str:
    lo, hi = sd.listing_bounds(product.key, stars)
    return "\n".join(
        [
            f"{product.emoji} <b>{product.name}</b> {_stars(stars)} — موجودی: {_n(have)}",
            "",
            f"📊 قیمت بازار: {_money(sd.market_price(product.key, stars))}",
            f"👥 آگهی کاربران: بین {_money(lo)} تا {_money(hi)} (قیمت دلخواه خودت)",
            f"{NPC}: فروش فوری هرکدام {_money(sd.npc_buy_price(product.key, stars))} (کمتر از بازار)",
        ]
    )


def npc_sold(product: ProductDef, stars: int, quantity: int, total: int) -> str:
    return f"{sd.NPC_EMOJI} {_n(quantity)} {product.name} {_stars(stars)} به {sd.NPC_NAME} فروختی و {_money(total)} گرفتی."


def price_prompt_page(product: ProductDef, stars: int, quantity: int) -> str:
    lo, hi = sd.listing_bounds(product.key, stars)
    return "\n".join(
        [
            f"📝 <b>ثبت آگهی: {product.emoji} {product.name} {_stars(stars)} × {_n(quantity)}</b>",
            "",
            f"📊 قیمت بازار: {_money(sd.market_price(product.key, stars))}",
            f"✅ قیمت مجاز هر عدد: از {_money(lo)} تا {_money(hi)}",
            "",
            "👇 روی همین پیام <b>ریپلای</b> کن و قیمت هر عدد رو (فقط عدد) بنویس.",
        ]
    )


def listing_created(product: ProductDef, stars: int, quantity: int, unit_price: int) -> str:
    return (
        f"✅ آگهی ثبت شد: {product.emoji} {product.name} {_stars(stars)} × {_n(quantity)}\n"
        f"💰 هرکدام {_money(unit_price)}\n"
        "برای مدیریت آگهی‌ها: «فروشگاه» ← «آگهی‌های من»"
    )


def price_out_of_range(limit: int, too_low: bool) -> str:
    if too_low:
        return f"⚠️ قیمت پایین‌تر از حداقل مجازه. حداقل: {_money(limit)}\nدوباره روی پیام پنل ریپلای کن و قیمت رو بنویس."
    return f"⚠️ قیمت بالاتر از حداکثر مجازه. حداکثر: {_money(limit)}\nدوباره روی پیام پنل ریپلای کن و قیمت رو بنویس."


PRICE_NOT_A_NUMBER = "⚠️ فقط یک عدد بنویس (مثلاً ۲۵۰۰)."
NOT_ENOUGH_STOCK = "📦 موجودی کافی نداری."
TOO_MANY_LISTINGS = f"📋 حداکثر {sd.MAX_LISTINGS_PER_USER} آگهی هم‌زمان می‌تونی داشته باشی."
LISTING_GONE = "این آگهی دیگه وجود نداره."
OWN_LISTING = "این آگهی خودته."


def insufficient_toman(missing: int) -> str:
    return f"💰 تومانت کافی نیست. {_money(missing)} کم داری."


# ---------------------------------------------------------------------------
# آگهی‌های من
# ---------------------------------------------------------------------------


def my_listings_page(listings: list[object]) -> str:
    lines = ["📋 <b>آگهی‌های من</b>", ""]
    if not listings:
        lines.append("آگهی فعالی نداری.")
    for l in listings:
        p = jd.PRODUCT_BY_KEY.get(l.product_key)
        if p:
            lines.append(f"  {p.emoji} {p.name} {_stars(l.stars)} × {_n(l.quantity)} — هرکدام {_money(l.unit_price)}")
    if listings:
        lines += ["", "با زدن دکمه، آگهی لغو می‌شه و کالا به انبارت برمی‌گرده."]
    return "\n".join(lines)


def listing_cancelled() -> str:
    return "↩️ آگهی لغو شد و کالا به انبارت برگشت."


NO_JOB_RAW = "برای خرید مواد اولیه باید شغل داشته باشی."
