"""
سرویس «حلقه ذکر» (Level 2).

`apply_circle_dhikr` تنها نقطه‌ی اتصال به ثبت ذکر است و باید همیشه از داخل همان
تراکنش موفقِ `process_activity` (بعد از ثبت قطعی یک ذکر معتبر) صدا زده شود — نه به‌عنوان
یک مسیر جداگانه. این تابع هیچ ذکری را خودش ثبت نمی‌کند؛ فقط روی یک ذکرِ از قبل موفق،
پیشرفت روزانه‌ی عضو و در صورت لزوم milestone پنج‌نفره را به‌روزرسانی می‌کند.

Atomicity: چون این تابع همیشه داخل همان تراکنش BEGIN IMMEDIATE فعالیت اصلی صدا زده
می‌شود (bot/database/engine.py)، بررسی «آیا milestone امروز پرداخت شده» و پرداخت آن
به‌صورت اتمیک انجام می‌شود و race condition روی milestone ممکن نیست.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DhikrCircle, DhikrCircleMember, User
from bot.domain import dhikr_circle as circle_domain
from bot.domain import dua_queue as dua_queue_domain  # tehran_date_str مشترک
from bot.domain.dhikr_data import CIRCLE_DISPLAY_DHIKR_KEYS, DHIKR_BY_KEY, DhikrDefinition

# مدت زمانی که ذکر تصادفی نمایشی («حلقه ذکر») برای یک کاربر ثابت می‌ماند.
CIRCLE_DISPLAY_DHIKR_STICKY_DURATION = timedelta(hours=24)


async def get_or_assign_display_dhikr(
    session: AsyncSession, user: User, now: datetime | None = None
) -> DhikrDefinition:
    """
    ذکر روزانه‌ی نمایشی را برمی‌گرداند.

    اگر کاربر عضو حلقه باشد، انتخاب ذکر در سطح همان حلقه مشترک است:
    از ذکرِ پایدارِ سازنده‌ی حلقه به‌عنوان منبع استفاده می‌کنیم و همان انتخاب را
    روی کاربر فعلی هم sync می‌کنیم. بنابراین همه‌ی اعضای یک حلقه دقیقاً همان ذکری
    را می‌بینند و همان ذکر را می‌توانند ثبت کنند.

    برای کاربری که عضو حلقه نیست، رفتار قبلی (انتخاب مستقلِ کاربر) حفظ می‌شود.
    """
    now = now or datetime.now(timezone.utc)

    source_user = user

    # ذکر حلقه باید بین همه‌ی اعضا مشترک باشد. چون creator_user_id روی خودِ
    # DhikrCircle پایدار است، حتی اگر سازنده بعداً از حلقه خارج شود نیز انتخاب
    # روزانه‌ی همان حلقه حفظ می‌شود و نیازی به migration جدید نداریم.
    if user.active_circle_id is not None:
        circle = await session.get(DhikrCircle, user.active_circle_id)
        if circle is not None:
            creator = await session.get(User, circle.creator_user_id)
            if creator is not None:
                source_user = creator

    assigned_at = source_user.circle_display_dhikr_assigned_at
    if assigned_at is not None and assigned_at.tzinfo is None:
        assigned_at = assigned_at.replace(tzinfo=timezone.utc)

    needs_new = (
        source_user.circle_display_dhikr_key is None
        or source_user.circle_display_dhikr_key not in DHIKR_BY_KEY
        or assigned_at is None
        or (now - assigned_at) >= CIRCLE_DISPLAY_DHIKR_STICKY_DURATION
    )

    if needs_new:
        source_user.circle_display_dhikr_key = random.choice(CIRCLE_DISPLAY_DHIKR_KEYS)
        source_user.circle_display_dhikr_assigned_at = now

    # انتخاب منبع را روی کاربر فعلی هم sync می‌کنیم تا validation پیام ذکر
    # دقیقاً با همان متنی که در پنل نمایش داده شده منطبق باشد.
    if user is not source_user:
        user.circle_display_dhikr_key = source_user.circle_display_dhikr_key
        user.circle_display_dhikr_assigned_at = source_user.circle_display_dhikr_assigned_at

    await session.flush()

    return DHIKR_BY_KEY[source_user.circle_display_dhikr_key]


# ---------------------------------------------------------------------------
# ساخت حلقه
# ---------------------------------------------------------------------------


class CreateCircleResult:
    SUCCESS = "success"
    ALREADY_IN_CIRCLE = "already_in_circle"
    FULL = "full"
    DAILY_LIMIT = "daily_limit"


@dataclass
class CreateCircleOutcome:
    result: str
    circle: DhikrCircle | None = None
    available_at: datetime | None = None


async def create_circle(
    session: AsyncSession,
    creator: User,
    name: str = "حلقه ذکر",
    now: datetime | None = None,
) -> CreateCircleOutcome:
    now = now or datetime.now(timezone.utc)
    if creator.active_circle_id is not None:
        return CreateCircleOutcome(result=CreateCircleResult.ALREADY_IN_CIRCLE)

    current_count = await _reset_expired_user_quota(creator, now)
    if current_count >= circle_domain.CIRCLE_DAILY_TARGET:
        started = creator.circle_daily_dhikr_started_at
        available_at = started + circle_domain.CIRCLE_USER_QUOTA_WINDOW if started else now
        return CreateCircleOutcome(result=CreateCircleResult.DAILY_LIMIT, available_at=available_at)

    name = " ".join(name.strip().split())
    if not name or len(name) > 40:
        name = "حلقه ذکر"
    existing = await session.scalar(select(func.count(DhikrCircle.id)).where(DhikrCircle.name == name))
    if existing:
        base = name
        index = 2
        while await session.scalar(select(DhikrCircle.id).where(DhikrCircle.name == name).limit(1)):
            suffix = f" {index}"
            name = (base[: 40 - len(suffix)] + suffix).strip()
            index += 1
    circle = DhikrCircle(
        creator_user_id=creator.id,
        created_at=now,
        milestone_paid_date=None,
        name=name,
        group_bonus_blocked_date=None,
        started_at=None,
        expires_at=None,
    )
    session.add(circle)
    await session.flush()
    member = DhikrCircleMember(
        circle_id=circle.id,
        user_id=creator.id,
        joined_at=now,
        status=circle_domain.MEMBER_STATUS_ACTIVE,
        daily_count=current_count,
        daily_date=creator.circle_daily_dhikr_started_at.isoformat() if creator.circle_daily_dhikr_started_at else None,
    )
    session.add(member)
    creator.active_circle_id = circle.id
    await session.flush()
    return CreateCircleOutcome(result=CreateCircleResult.SUCCESS, circle=circle)


# ---------------------------------------------------------------------------
# عضویت
# ---------------------------------------------------------------------------


class JoinCircleResult:
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ALREADY_IN_CIRCLE = "already_in_circle"
    FULL = "full"
    COOLDOWN = "cooldown"


@dataclass
class JoinCircleOutcome:
    result: str
    circle: DhikrCircle | None = None
    member: DhikrCircleMember | None = None
    cooldown_until: datetime | None = None


async def join_circle(
    session: AsyncSession, user: User, circle_id: int, now: datetime | None = None
) -> JoinCircleOutcome:
    now = now or datetime.now(timezone.utc)
    if user.active_circle_id is not None:
        return JoinCircleOutcome(result=JoinCircleResult.ALREADY_IN_CIRCLE)
    circle = await session.get(DhikrCircle, circle_id)
    if circle is None:
        return JoinCircleOutcome(result=JoinCircleResult.NOT_FOUND)
    if circle.expires_at is not None:
        expires_at = circle.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            return JoinCircleOutcome(result=JoinCircleResult.NOT_FOUND)
    current_count = await _reset_expired_user_quota(user, now)
    member = DhikrCircleMember(
        circle_id=circle.id,
        user_id=user.id,
        joined_at=now,
        status=circle_domain.MEMBER_STATUS_ACTIVE,
        daily_count=current_count,
        daily_date=user.circle_daily_dhikr_started_at.isoformat() if user.circle_daily_dhikr_started_at else None,
    )
    session.add(member)
    user.active_circle_id = circle.id
    await session.flush()
    return JoinCircleOutcome(result=JoinCircleResult.SUCCESS, circle=circle, member=member)


async def get_active_membership(session: AsyncSession, user: User) -> DhikrCircleMember | None:
    if user.active_circle_id is None:
        return None
    result = await session.execute(
        select(DhikrCircleMember).where(
            DhikrCircleMember.circle_id == user.active_circle_id,
            DhikrCircleMember.user_id == user.id,
            DhikrCircleMember.status == circle_domain.MEMBER_STATUS_ACTIVE,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# خروج / حذف عضو
# ---------------------------------------------------------------------------


class LeaveCircleResult:
    SUCCESS = "success"
    NOT_IN_CIRCLE = "not_in_circle"


@dataclass
class LeaveCircleOutcome:
    result: str
    unlock_at: datetime | None = None


async def leave_circle(session: AsyncSession, user: User, now: datetime | None = None) -> LeaveCircleOutcome:
    """
    خروج از حلقه.

    اگر درخواست‌کننده سازنده‌ی حلقه باشد، «خروج» به معنی حذف کامل حلقه است:
    تمام اعضا از حلقه خارج می‌شوند، active_circle_id همه پاک می‌شود و خود حلقه
    و membershipهای فعال/قدیمی آن حذف می‌شوند. بنابراین هیچ عضو شبحی باقی نمی‌ماند
    و اعضای سابق می‌توانند بلافاصله توسط یک حلقه‌ی جدید دعوت شوند.
    """
    now = now or datetime.now(timezone.utc)
    member = await get_active_membership(session, user)
    if member is None:
        # حتی اگر active_circle_id قدیمی باشد، آن را پاک کن.
        user.active_circle_id = None
        return LeaveCircleOutcome(result=LeaveCircleResult.NOT_IN_CIRCLE)

    circle = await session.get(DhikrCircle, member.circle_id)
    if circle is None:
        user.active_circle_id = None
        await session.delete(member)
        await session.flush()
        return LeaveCircleOutcome(result=LeaveCircleResult.SUCCESS)

    # سازنده با خروج، کل حلقه را حذف می‌کند و همه اعضا آزاد می‌شوند.
    if circle.creator_user_id == user.id:
        result_all_members = await session.execute(
            select(DhikrCircleMember).where(DhikrCircleMember.circle_id == circle.id)
        )
        all_members = list(result_all_members.scalars().all())
        for old_member in all_members:
            old_user = await session.get(User, old_member.user_id)
            if old_user is not None and old_user.active_circle_id == circle.id:
                old_user.active_circle_id = None
            await session.delete(old_member)
        await session.delete(circle)
        await session.flush()
        return LeaveCircleOutcome(result=LeaveCircleResult.SUCCESS)

    # عضو عادی فقط خودش را از حلقه خارج می‌کند.
    member.status = circle_domain.MEMBER_STATUS_LEFT
    member.left_at = now
    member.left_reason = circle_domain.LEAVE_REASON_SELF
    user.active_circle_id = None

    active_count = await session.scalar(select(func.count(DhikrCircleMember.id)).where(
        DhikrCircleMember.circle_id == circle.id,
        DhikrCircleMember.status == circle_domain.MEMBER_STATUS_ACTIVE,
    ))
    if (active_count or 0) == 0:
        result_all_members = await session.execute(
            select(DhikrCircleMember).where(DhikrCircleMember.circle_id == circle.id)
        )
        for old_member in result_all_members.scalars().all():
            old_user = await session.get(User, old_member.user_id)
            if old_user is not None and old_user.active_circle_id == circle.id:
                old_user.active_circle_id = None
            await session.delete(old_member)
        await session.delete(circle)

    await session.flush()
    return LeaveCircleOutcome(result=LeaveCircleResult.SUCCESS)


class RemoveMemberResult:
    SUCCESS = "success"
    NOT_CREATOR = "not_creator"
    TARGET_NOT_FOUND = "target_not_found"
    LOCKED = "locked"
    CANNOT_REMOVE_SELF = "cannot_remove_self"


@dataclass
class RemoveMemberOutcome:
    result: str
    unlock_at: datetime | None = None


async def remove_member(
    session: AsyncSession,
    creator: User,
    circle: DhikrCircle,
    target_user_id: int,
    now: datetime | None = None,
) -> RemoveMemberOutcome:
    now = now or datetime.now(timezone.utc)

    if circle.creator_user_id != creator.id:
        return RemoveMemberOutcome(result=RemoveMemberResult.NOT_CREATOR)

    if target_user_id == creator.id:
        return RemoveMemberOutcome(result=RemoveMemberResult.CANNOT_REMOVE_SELF)

    result = await session.execute(
        select(DhikrCircleMember).where(
            DhikrCircleMember.circle_id == circle.id,
            DhikrCircleMember.user_id == target_user_id,
            DhikrCircleMember.status == circle_domain.MEMBER_STATUS_ACTIVE,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        return RemoveMemberOutcome(result=RemoveMemberResult.TARGET_NOT_FOUND)

    member.status = circle_domain.MEMBER_STATUS_LEFT
    member.left_at = now
    member.left_reason = circle_domain.LEAVE_REASON_REMOVED
    target_user = await session.get(User, target_user_id)
    if target_user is not None:
        target_user.active_circle_id = None
    active_count = await session.scalar(select(func.count(DhikrCircleMember.id)).where(
        DhikrCircleMember.circle_id == circle.id,
        DhikrCircleMember.status == circle_domain.MEMBER_STATUS_ACTIVE,
    ))
    if (active_count or 0) == 0:
        result_all_members = await session.execute(
            select(DhikrCircleMember).where(DhikrCircleMember.circle_id == circle.id)
        )
        for old_member in result_all_members.scalars().all():
            old_user = await session.get(User, old_member.user_id)
            if old_user is not None and old_user.active_circle_id == circle.id:
                old_user.active_circle_id = None
            await session.delete(old_member)
        await session.delete(circle)
    await session.flush()

    return RemoveMemberOutcome(result=RemoveMemberResult.SUCCESS)


# ---------------------------------------------------------------------------
# ثبت پیشرفت روزانه + bonus + milestone (فراخوانی از activity_service._register_dhikr)
# ---------------------------------------------------------------------------


@dataclass
class MilestonePayout:
    circle_id: int
    winners: list[User] = field(default_factory=list)


@dataclass
class CircleActivityResult:
    applied: bool = False
    bonus_noor: int = 0
    daily_count: int = 0
    daily_target: int = circle_domain.CIRCLE_DAILY_TARGET
    just_completed_today: bool = False
    milestone: MilestonePayout | None = None




async def get_circle_daily_count(
    session: AsyncSession, user: User, *, now: datetime
) -> int:
    started = user.circle_daily_dhikr_started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if started is None or now >= started + circle_domain.CIRCLE_USER_QUOTA_WINDOW:
        return 0
    return min(user.circle_daily_dhikr_count or 0, circle_domain.CIRCLE_DAILY_TARGET)


async def _reset_expired_user_quota(user: User, now: datetime) -> int:
    started = user.circle_daily_dhikr_started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if started is None or now >= started + circle_domain.CIRCLE_USER_QUOTA_WINDOW:
        user.circle_daily_dhikr_count = 0
        user.circle_daily_dhikr_started_at = None
        return 0
    return min(user.circle_daily_dhikr_count or 0, circle_domain.CIRCLE_DAILY_TARGET)


async def expire_expired_circles(session: AsyncSession, now: datetime | None = None) -> list[tuple[int, int]]:
    now = now or datetime.now(timezone.utc)
    result = await session.execute(select(DhikrCircle).where(DhikrCircle.expires_at.is_not(None)))
    circles = []
    for candidate in result.scalars().all():
        expires_at = candidate.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is not None and expires_at <= now:
            circles.append(candidate)
    targets = []
    for circle in circles:
        result_members = await session.execute(select(DhikrCircleMember).where(DhikrCircleMember.circle_id == circle.id))
        members = list(result_members.scalars().all())
        for member in members:
            if member.panel_chat_id is not None and member.panel_message_id is not None:
                targets.append((member.panel_chat_id, member.panel_message_id))
            user = await session.get(User, member.user_id)
            if user is not None and user.active_circle_id == circle.id:
                user.active_circle_id = None
            await session.delete(member)
        await session.delete(circle)
    if circles:
        await session.flush()
    return targets


async def apply_circle_dhikr(
    session: AsyncSession, user: User, *, now: datetime
) -> CircleActivityResult:
    if user.active_circle_id is None:
        return CircleActivityResult(applied=False)
    circle = await session.get(DhikrCircle, user.active_circle_id)
    if circle is None:
        user.active_circle_id = None
        return CircleActivityResult(applied=False)
    if circle.expires_at is not None:
        expires_at = circle.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            await expire_expired_circles(session, now)
            return CircleActivityResult(applied=False)

    member = await get_active_membership(session, user)
    if member is None:
        user.active_circle_id = None
        return CircleActivityResult(applied=False)

    count = await _reset_expired_user_quota(user, now)
    if count >= circle_domain.CIRCLE_DAILY_TARGET:
        return CircleActivityResult(applied=False, daily_count=count, daily_target=circle_domain.CIRCLE_DAILY_TARGET)

    if user.circle_daily_dhikr_started_at is None:
        user.circle_daily_dhikr_started_at = now
    user.circle_daily_dhikr_count = count + 1
    member.daily_count = user.circle_daily_dhikr_count
    member.daily_date = user.circle_daily_dhikr_started_at.isoformat()
    just_completed = member.daily_count == circle_domain.CIRCLE_DAILY_TARGET
    if just_completed:
        member.daily_completed_at = now

    if circle.started_at is None:
        circle.started_at = now
        circle.expires_at = now + circle_domain.CIRCLE_LIFETIME

    await session.flush()
    milestone = await _maybe_pay_milestone(session, circle.id) if just_completed else None
    return CircleActivityResult(
        applied=True,
        daily_count=member.daily_count,
        daily_target=circle_domain.CIRCLE_DAILY_TARGET,
        just_completed_today=just_completed,
        milestone=milestone,
    )

async def _maybe_pay_milestone(session: AsyncSession, circle_id: int) -> MilestonePayout | None:
    circle = await session.get(DhikrCircle, circle_id)
    if circle is None or circle.milestone_paid_date is not None or circle.group_bonus_blocked_date is not None:
        return None
    result = await session.execute(select(DhikrCircleMember).where(
        DhikrCircleMember.circle_id == circle_id,
        DhikrCircleMember.status == circle_domain.MEMBER_STATUS_ACTIVE,
        DhikrCircleMember.daily_count >= circle_domain.CIRCLE_DAILY_TARGET,
    ).order_by(DhikrCircleMember.daily_completed_at.asc()))
    completed = list(result.scalars().all())
    if len(completed) < circle_domain.CIRCLE_MILESTONE_MIN_MEMBERS:
        return None
    winners_members = completed[:circle_domain.CIRCLE_MILESTONE_MIN_MEMBERS]
    ids = [m.user_id for m in winners_members]
    result2 = await session.execute(select(User).where(User.id.in_(ids)))
    by_id = {u.id: u for u in result2.scalars().all()}
    winners = []
    for uid in ids:
        u = by_id.get(uid)
        if u is not None:
            u.noor_current += circle_domain.CIRCLE_MILESTONE_REWARD_PER_MEMBER
            u.noor_total_earned += circle_domain.CIRCLE_MILESTONE_REWARD_PER_MEMBER
            winners.append(u)
    circle.milestone_paid_date = datetime.now(timezone.utc).isoformat()
    await session.flush()
    return MilestonePayout(circle_id=circle_id, winners=winners)


# ---------------------------------------------------------------------------
# دریافت جایزه‌ی شخصی (دکمه‌ی «دریافت جایزه» در پنل)
# ---------------------------------------------------------------------------


class ClaimPersonalRewardResult:
    SUCCESS = "success"
    NOT_IN_CIRCLE = "not_in_circle"
    NOT_READY = "not_ready"  # هنوز امروز به ۱۰/۱۰ نرسیده
    ALREADY_CLAIMED = "already_claimed"


@dataclass
class ClaimPersonalRewardOutcome:
    result: str
    reward_noor: int = 0


async def claim_circle_personal_reward(
    session: AsyncSession, user: User, now: datetime | None = None
) -> ClaimPersonalRewardOutcome:
    """
    پرداخت پاداش شخصی ۲۵ نوری، فقط با کلیک کاربر روی دکمه‌ی «دریافت جایزه».
    باید داخل همان تراکنش BEGIN IMMEDIATE فعالیت/callback صدا زده شود تا دوبار
    کلیک همزمان (double click) دوبار پرداخت نکند.
    """
    now = now or datetime.now(timezone.utc)
    member = await get_active_membership(session, user)
    if member is None:
        return ClaimPersonalRewardOutcome(result=ClaimPersonalRewardResult.NOT_IN_CIRCLE)

    count = await _reset_expired_user_quota(user, now)
    if count < circle_domain.CIRCLE_DAILY_TARGET:
        return ClaimPersonalRewardOutcome(result=ClaimPersonalRewardResult.NOT_READY)
    reward_key = user.circle_daily_dhikr_started_at.isoformat() if user.circle_daily_dhikr_started_at else None
    if user.circle_personal_reward_date == reward_key:
        return ClaimPersonalRewardOutcome(result=ClaimPersonalRewardResult.ALREADY_CLAIMED)
    user.circle_personal_reward_date = reward_key
    user.noor_current += circle_domain.CIRCLE_PERSONAL_REWARD_NOOR
    user.noor_total_earned += circle_domain.CIRCLE_PERSONAL_REWARD_NOOR
    await session.flush()

    return ClaimPersonalRewardOutcome(
        result=ClaimPersonalRewardResult.SUCCESS,
        reward_noor=circle_domain.CIRCLE_PERSONAL_REWARD_NOOR,
    )


# ---------------------------------------------------------------------------
# اطلاعات نمایشی پنل
# ---------------------------------------------------------------------------


async def get_circle_with_members(
    session: AsyncSession, circle_id: int
) -> tuple[DhikrCircle | None, list[DhikrCircleMember]]:
    circle = await session.get(DhikrCircle, circle_id)
    if circle is None:
        return None, []
    result = await session.execute(
        select(DhikrCircleMember)
        .where(DhikrCircleMember.circle_id == circle_id, DhikrCircleMember.status == circle_domain.MEMBER_STATUS_ACTIVE)
        .order_by(DhikrCircleMember.joined_at.asc())
    )
    return circle, list(result.scalars().all())
