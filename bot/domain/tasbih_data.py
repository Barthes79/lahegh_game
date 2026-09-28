"""
جدول ۱۲ سطح تسبیح (بخش ۱۵ سند).

هر سطح یک cooldown ذکر (بر حسب ثانیه) دارد. هزینه‌ی ارتقا از سطح N به N+1
در upgrade_cost سطح N ذخیره شده (سطح ۱۲ چون آخرین سطح است upgrade_cost=None دارد).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TasbihLevel:
    level: int
    dhikr_cooldown_seconds: int
    upgrade_cost: int | None  # هزینه ارتقا به سطح بعدی؛ None برای سطح آخر


TASBIH_LEVELS: list[TasbihLevel] = [
    TasbihLevel(1, 10, 100),
    TasbihLevel(2, 10, 300),
    TasbihLevel(3, 10, 600),
    TasbihLevel(4, 10, 1000),
    TasbihLevel(5, 10, 1500),
    TasbihLevel(6, 10, 2200),
    TasbihLevel(7, 10, 3000),
    TasbihLevel(8, 10, 4000),
    TasbihLevel(9, 10, 5500),
    TasbihLevel(10, 10, 7500),
    TasbihLevel(11, 10, 10000),
    TasbihLevel(12, 10, None),
]

TASBIH_BY_LEVEL: dict[int, TasbihLevel] = {t.level: t for t in TASBIH_LEVELS}

TASBIH_MAX_LEVEL = 12

# cooldown پایه‌ی ذکر وقتی تسبیح هنوز unlock نشده (سطح ۰) — برابر با سطح ۱ (بخش ۷: cooldown پایه ۵:۰۰)
DEFAULT_DHIKR_COOLDOWN_SECONDS = 10


def get_dhikr_cooldown_for_level(tasbih_level: int) -> int:
    """cooldown ذکر بر اساس سطح فعلی تسبیح کاربر (۰ = هنوز باز نشده -> مقدار پیش‌فرض)."""
    if tasbih_level <= 0:
        return DEFAULT_DHIKR_COOLDOWN_SECONDS
    level = TASBIH_BY_LEVEL.get(tasbih_level)
    return level.dhikr_cooldown_seconds if level else DEFAULT_DHIKR_COOLDOWN_SECONDS


def get_upgrade_cost(current_level: int) -> int | None:
    """هزینه‌ی ارتقا از سطح فعلی به سطح بعدی؛ None اگر سطح آخر است یا هنوز باز نشده."""
    if current_level <= 0:
        return None
    level = TASBIH_BY_LEVEL.get(current_level)
    return level.upgrade_cost if level else None
