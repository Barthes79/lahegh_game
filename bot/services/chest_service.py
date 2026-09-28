"""
منطق باز کردن صندوقچه (بخش ۱۶ سند).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.database.models import Chest, User
from bot.domain import chest as chest_domain


class ChestOpenResult:
    SUCCESS = "success"
    NOT_OWNER = "not_owner"
    ALREADY_OPENED = "already_opened"
    EXPIRED = "expired"


@dataclass
class ChestOpenOutcome:
    result: str
    reward_noor: int = 0
    noor_current: int = 0


def open_chest(chest: Chest, user: User, requester_telegram_id: int) -> ChestOpenOutcome:
    if user.telegram_id != requester_telegram_id:
        return ChestOpenOutcome(result=ChestOpenResult.NOT_OWNER)

    if chest.opened:
        return ChestOpenOutcome(result=ChestOpenResult.ALREADY_OPENED)

    if chest_domain.is_expired(chest.expires_at):
        return ChestOpenOutcome(result=ChestOpenResult.EXPIRED)

    reward = chest_domain.roll_chest_reward()
    chest.opened = True
    chest.opened_at = datetime.now(timezone.utc)
    chest.reward_noor = reward

    user.noor_current += reward
    user.noor_total_earned += reward

    return ChestOpenOutcome(result=ChestOpenResult.SUCCESS, reward_noor=reward, noor_current=user.noor_current)
