"""
منطق ارتقای تسبیح (بخش ۱۵ سند).

نکته‌ی مهم: cooldown ذکرِ در حال اجرا (اگر کاربر همین الان در cooldown باشد) تغییر نمی‌کند،
چون آن مقدار در لحظه‌ی ثبت همان ذکر در User.last_dhikr_cooldown_seconds فریز شده است.
ارتقای تسبیح فقط سطح تسبیح را عوض می‌کند؛ ذکر *بعدی* با cooldown جدید محاسبه و فریز خواهد شد.
"""
from __future__ import annotations

from dataclasses import dataclass

from bot.database.models import User
from bot.domain.tasbih_data import TASBIH_MAX_LEVEL, get_dhikr_cooldown_for_level, get_upgrade_cost


class TasbihUpgradeResult:
    SUCCESS = "success"
    MAX_LEVEL = "max_level"
    INSUFFICIENT_NOOR = "insufficient_noor"
    NOT_UNLOCKED = "not_unlocked"


@dataclass
class TasbihUpgradeOutcome:
    result: str
    new_level: int = 0
    new_cooldown_seconds: int = 0


def upgrade_tasbih(user: User) -> TasbihUpgradeOutcome:
    if not user.tasbih_unlocked or user.tasbih_level <= 0:
        return TasbihUpgradeOutcome(result=TasbihUpgradeResult.NOT_UNLOCKED)

    if user.tasbih_level >= TASBIH_MAX_LEVEL:
        return TasbihUpgradeOutcome(result=TasbihUpgradeResult.MAX_LEVEL)

    cost = get_upgrade_cost(user.tasbih_level)
    if cost is None:
        return TasbihUpgradeOutcome(result=TasbihUpgradeResult.MAX_LEVEL)

    if user.noor_current < cost:
        return TasbihUpgradeOutcome(result=TasbihUpgradeResult.INSUFFICIENT_NOOR)

    user.noor_current -= cost
    user.tasbih_level += 1

    return TasbihUpgradeOutcome(
        result=TasbihUpgradeResult.SUCCESS,
        new_level=user.tasbih_level,
        new_cooldown_seconds=get_dhikr_cooldown_for_level(user.tasbih_level),
    )
