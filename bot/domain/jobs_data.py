"""
داده‌ها و قوانین خالص مشاغل Level 3 (بدون وابستگی به تلگرام/دیتابیس).

۵ شغل، هرکدام ۴ محصول که در سطح ۳/۴/۵/۶ باز می‌شوند. هر شغل یک ابزار دارد که با نور
ارتقا پیدا می‌کند و کیفیت (ستاره) و تعداد محصول را بهتر می‌کند.

⚠️ مقدارهایی که در سند مشخص نبود (هزینه‌ها، قیمت‌ها، تعداد تولید هر دفعه) با علامت
[PLACEHOLDER] مشخص شده‌اند و فقط همین‌جا تعریف می‌شوند تا راحت عوض شوند.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# مقدارهای قابل تنظیم
# ---------------------------------------------------------------------------

JOB_UNLOCK_LEVEL = 3  # شغل از سطح ۳ قابل انتخاب است

JOB_SELECT_COST_NOOR = 500  # [PLACEHOLDER] «با پرداخت نور» — مقدار در سند نیامده
STARTING_TOMAN = 3000  # [PLACEHOLDER] تومان اولیه هنگام انتخاب شغل تا بتواند اولین مواد اولیه را بخرد

DHIKR_PER_BATCH = 5  # تعداد ذکر لازم برای هر بار تولید (سند: «مثلاً ۵ بار»)

TOOL_START_LEVEL = 1
TOOL_MAX_LEVEL = 5
# هزینه‌ی نور برای ارتقای ابزار از سطح N به N+1  [PLACEHOLDER]
TOOL_UPGRADE_COST_NOOR: dict[int, int] = {1: 400, 2: 800, 3: 1200, 4: 1800}
# تعداد محصولی که هر بار تولید می‌دهد، بر اساس سطح ابزار  [PLACEHOLDER]
TOOL_YIELD_BY_LEVEL: dict[int, int] = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}

# ضریب قیمت فروش بر اساس ستاره  [PLACEHOLDER]
STAR_PRICE_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 1.5, 3: 2.0, 4: 3.0, 5: 4.0}

# جدول شانس کیفیت بر اساس سطح ابزار (سند؛ برای همه‌ی مشاغل یکسان است)
# {tool_level: {stars: percent}}
QUALITY_CHANCES: dict[int, dict[int, int]] = {
    1: {1: 100},
    2: {1: 95, 2: 5},
    3: {1: 70, 2: 20, 3: 10},
    4: {1: 50, 2: 25, 3: 15, 4: 10},
    5: {1: 5, 2: 20, 3: 35, 4: 15, 5: 25},
}


# ---------------------------------------------------------------------------
# تعریف شغل‌ها و محصولات
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductDef:
    key: str
    name: str
    emoji: str
    unlock_level: int  # ۳ / ۴ / ۵ / ۶
    raw_price: int  # قیمت یک واحد ماده‌ی اولیه (تومان)  [PLACEHOLDER]
    sell_price: int  # قیمت پایه‌ی فروش هر واحد یک‌ستاره (تومان)  [PLACEHOLDER]


@dataclass(frozen=True)
class JobDef:
    key: str
    name: str
    emoji: str
    tool_name: str
    raw_name: str  # نام ماده‌ی اولیه‌ی شغل (بذر/علوفه/...)
    supplier: str  # جایی که ماده‌ی اولیه از آن می‌آید
    produce_verb: str  # جمله‌ی حال‌وهوایی هنگام تولید
    products: tuple[ProductDef, ...]


def _products(prefix: str, items: list[tuple[str, str, str]]) -> tuple[ProductDef, ...]:
    # قیمت‌ها با سطح محصول بالا می‌روند  [PLACEHOLDER]
    raw_prices = [1000, 2000, 3500, 5500]
    sell_prices = [1600, 3200, 5600, 8800]
    return tuple(
        ProductDef(
            key=f"{prefix}_{key}",
            name=name,
            emoji=emoji,
            unlock_level=3 + i,
            raw_price=raw_prices[i],
            sell_price=sell_prices[i],
        )
        for i, (key, name, emoji) in enumerate(items)
    )


JOBS: tuple[JobDef, ...] = (
    JobDef(
        key="farmer",
        name="کشاورز",
        emoji="🌾",
        tool_name="بیل",
        raw_name="بذر",
        supplier="مارکت بذر",
        produce_verb="بذر کاشته شد؛ ذکر بگو تا محصول برسه",
        products=_products(
            "farmer",
            [
                ("potato", "سیب‌زمینی", "🥔"),
                ("greens", "سبزی", "🥬"),
                ("legumes", "حبوبات", "🫘"),
                ("rice", "برنج", "🍚"),
            ],
        ),
    ),
    JobDef(
        key="rancher",
        name="دامدار",
        emoji="🐄",
        tool_name="اصطبل",
        raw_name="علوفه",
        supplier="مارکت علوفه",
        produce_verb="علوفه جلوی دام‌ها ریخته شد؛ ذکر بگو تا محصول آماده بشه",
        products=_products(
            "rancher",
            [
                ("chicken", "مرغ", "🐔"),
                ("dairy", "لبنیات", "🥛"),
                ("cow", "گاو", "🐄"),
                ("sheep", "گوسفند", "🐑"),
            ],
        ),
    ),
    JobDef(
        key="grocer",
        name="بقال",
        emoji="🏪",
        tool_name="یخچال",
        raw_name="جنس",
        supplier="کارخونه",
        produce_verb="ماشین بار راه افتاد؛ ذکر بگو تا برسه به مغازه",
        products=_products(
            "grocer",
            [
                ("bread", "نون", "🍞"),
                ("sandwich", "ساندویچ", "🥪"),
                ("tomato_paste", "رب", "🍅"),
                ("soda", "نوشابه", "🥤"),
            ],
        ),
    ),
    JobDef(
        key="attar",
        name="عطار",
        emoji="🌿",
        tool_name="بلندر",
        raw_name="گیاه",
        supplier="مارکت گیاه",
        produce_verb="گیاه‌ها توی بلندر ریخته شد؛ ذکر بگو تا پودر بشن",
        products=_products(
            "attar",
            [
                ("salt", "نمک", "🧂"),
                ("turmeric", "زردچوبه", "🟡"),
                ("curry", "ادویه کاری", "🌶"),
                ("saffron", "زعفران", "🌺"),
            ],
        ),
    ),
    JobDef(
        key="disposable",
        name="یک‌بارمصرف‌فروش",
        emoji="🛍",
        tool_name="دستگاه تولید",
        raw_name="پلاستیک",
        supplier="کارخونه پلاستیک",
        produce_verb="پلاستیک وارد دستگاه شد؛ ذکر بگو تا تولید تموم بشه",
        products=_products(
            "disposable",
            [
                ("freezer_bag", "کیسه فریزر", "🛍"),
                ("cup", "لیوان", "🥛"),
                ("bowl", "کاسه", "🥣"),
                ("plate", "بشقاب", "🍽"),
            ],
        ),
    ),
)

JOB_BY_KEY: dict[str, JobDef] = {j.key: j for j in JOBS}
PRODUCT_BY_KEY: dict[str, ProductDef] = {p.key: p for j in JOBS for p in j.products}
JOB_OF_PRODUCT: dict[str, JobDef] = {p.key: j for j in JOBS for p in j.products}


# ---------------------------------------------------------------------------
# توابع خالص
# ---------------------------------------------------------------------------


def unlocked_products(job: JobDef, user_level: int) -> list[ProductDef]:
    return [p for p in job.products if p.unlock_level <= user_level]


def max_tool_level_for_user_level(user_level: int) -> int:
    """
    در هر سطح فقط یک بار می‌شود ابزار را ارتقا داد:
    سطح ۳ -> ابزار تا ۲، سطح ۴ -> تا ۳، سطح ۵ -> تا ۴، سطح ۶ -> تا ۵.
    """
    return max(TOOL_START_LEVEL, min(TOOL_MAX_LEVEL, user_level - 1))


def get_tool_upgrade_cost(tool_level: int) -> int | None:
    return TOOL_UPGRADE_COST_NOOR.get(tool_level)


def roll_quality(tool_level: int, rng: random.Random | None = None) -> int:
    """یک ستاره‌ی کیفیت را طبق جدول شانسِ سطح ابزار می‌اندازد."""
    rng = rng or random
    table = QUALITY_CHANCES.get(tool_level) or QUALITY_CHANCES[1]
    stars = list(table.keys())
    weights = list(table.values())
    return rng.choices(stars, weights=weights, k=1)[0]


def roll_batch(tool_level: int, rng: random.Random | None = None) -> dict[int, int]:
    """نتیجه‌ی یک بار تولید: {stars: quantity}. تعداد از سطح ابزار، کیفیت هر واحد جداگانه."""
    count = TOOL_YIELD_BY_LEVEL.get(tool_level, 1)
    result: dict[int, int] = {}
    for _ in range(count):
        s = roll_quality(tool_level, rng)
        result[s] = result.get(s, 0) + 1
    return result


def get_sell_price(product: ProductDef, stars: int) -> int:
    return int(round(product.sell_price * STAR_PRICE_MULTIPLIER.get(stars, 1.0)))
