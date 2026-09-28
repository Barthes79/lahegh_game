"""
سرویس «التماس دعا» (Level 2؛ نام داخلی: dua_queue).

نکته‌ی مهم معماری: ثبت ذکرِ پاسخ‌دهنده هرگز به‌صورت مستقیم/موازی انجام نمی‌شود؛
`answer_dua_queue` دقیقاً از همان `process_activity` (مسیر اصلی Level 1) استفاده می‌کند
تا cooldown شخصی، سهمیه‌ی روزانه و idempotency (طبق بخش ۲۰) دقیقاً طبق همان قوانین فعلی
رعایت شوند. تنها کاری که این سرویس اضافه می‌کند: انتخاب ذکر تصادفی پنل، تطبیق متن ریپلای با
آن ذکر، ثبت پاسخ، و پاداش صاحب پنل (۱۵ نور به‌ازای هر پاسخ + ۲۵ نور بونوس در پاسخ پنجم).

مکانیزم پاسخ: پاسخ‌دهنده متن ذکرِ نمایش‌داده‌شده روی پنل را کپی می‌کند و روی خودِ پیام پنل
ریپلای می‌زند. ذکرهای این قابلیت (DUA_QUEUE_DHIKR_LIST) داخل DHIKR_LIST نیستند، پس بیرون
از پنل هیچ نوری نمی‌دهند؛ از طریق `forced_dhikr` به process_activity داده می‌شوند.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DuaQueue, DuaQueueAnswer, DuaQueueExtraMessage, User
from bot.domain import dua_queue as dua_queue_domain
from bot.domain.dhikr_data import DUA_QUEUE_DHIKR_BY_KEY, DUA_QUEUE_DHIKR_LIST, DhikrDefinition
from bot.domain.normalization import normalize_text
from bot.services.activity_service import ActivityOutcome, OutcomeStatus, process_activity
from bot.services.user_service import get_or_create_user


# ---------------------------------------------------------------------------
# شمارش «عضو فعال» گروه (فقط برای آمار/تست؛ دیگر شرط ساخت پنل نیست)
# ---------------------------------------------------------------------------


async def count_active_members(session: AsyncSession, chat_id: int) -> int:
    """تعداد کاربران متفاوتی که آخرین فعالیت معتبرشان در همین chat_id بوده (User.active_chat_id)."""
    result = await session.execute(
        select(func.count(User.id)).where(User.active_chat_id == chat_id)
    )
    return result.scalar_one() or 0


async def _find_open_queue(
    session: AsyncSession, owner_user_id: int, now: datetime
) -> DuaQueue | None:
    """
    پنلِ هنوز بازِ این کاربر (نه بسته، نه پر، نه منقضی) را برمی‌گرداند؛ در غیر این صورت None.
    برای اینکه صاحب پنل بتواند دوباره دستور «التماس دعا» را بزند و فقط پنلش را ببیند.
    """
    result = await session.execute(
        select(DuaQueue)
        .where(DuaQueue.owner_user_id == owner_user_id, DuaQueue.closed.is_(False))
        .order_by(DuaQueue.id.desc())
    )
    for queue in result.scalars().all():
        if dua_queue_domain.is_queue_open(
            closed=queue.closed,
            answers_count=queue.answers_count,
            expires_at=queue.expires_at,
            now=now,
        ):
            return queue
    return None


async def _has_recent_queue(session: AsyncSession, owner_user_id: int, now: datetime) -> bool:
    cutoff = now - dua_queue_domain.QUEUE_OWNER_COOLDOWN
    result = await session.execute(
        select(DuaQueue.id)
        .where(DuaQueue.owner_user_id == owner_user_id, DuaQueue.created_at >= cutoff)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def get_queue_dhikr(queue: DuaQueue) -> DhikrDefinition | None:
    """ذکر این پنل؛ برای پنل‌های قدیمی (بدون dhikr_key) None است."""
    if queue.dhikr_key is None:
        return None
    return DUA_QUEUE_DHIKR_BY_KEY.get(queue.dhikr_key)


# ---------------------------------------------------------------------------
# اطلاعات نمایشی پنل (نام پاسخ‌دهنده‌ها + نور دریافتی صاحب پنل)
# ---------------------------------------------------------------------------


@dataclass
class PanelView:
    owner_telegram_id: int | None
    owner_name: str | None
    # به ترتیب زمان پاسخ: (telegram_id, first_name)
    responders: list[tuple[int, str | None]]
    # نوری که صاحب پنل از همین پنل گرفته (۱۵ به‌ازای هر پاسخ + ۲۵ بونوس اگر پنل کامل شده)
    owner_earned: int


def compute_owner_earned(answers_count: int) -> int:
    earned = answers_count * dua_queue_domain.QUEUE_OWNER_REWARD_PER_ANSWER
    if answers_count >= dua_queue_domain.QUEUE_MAX_ANSWERS:
        earned += dua_queue_domain.QUEUE_OWNER_COMPLETION_BONUS
    return earned


async def get_panel_view(session: AsyncSession, queue: DuaQueue) -> PanelView:
    owner = await session.get(User, queue.owner_user_id)
    rows = await session.execute(
        select(User.telegram_id, User.first_name)
        .join(DuaQueueAnswer, DuaQueueAnswer.responder_user_id == User.id)
        .where(DuaQueueAnswer.queue_id == queue.id)
        .order_by(DuaQueueAnswer.id)
    )
    return PanelView(
        owner_telegram_id=owner.telegram_id if owner else None,
        owner_name=owner.first_name if owner else None,
        responders=[(tg_id, name) for tg_id, name in rows.all()],
        owner_earned=compute_owner_earned(queue.answers_count),
    )


# ---------------------------------------------------------------------------
# بستن پنل‌های منقضی
# ---------------------------------------------------------------------------


async def close_expired_queues(session: AsyncSession, now: datetime | None = None) -> list[DuaQueue]:
    """
    برای job زمان‌بندی‌شده (bot/jobs/scheduler.py): تمام پنل‌های باز و منقضی‌شده را می‌بندد
    و لیست همان پنل‌ها را برمی‌گرداند تا caller (که به bot دسترسی دارد) پیام پنل را edit کند.

    Idempotent: فقط پنل‌هایی که closed=False هستند بررسی می‌شوند، پس یک پنل هرگز دوبار
    پردازش نمی‌شود.
    """
    now = now or datetime.now(timezone.utc)
    result = await session.execute(select(DuaQueue).where(DuaQueue.closed.is_(False)))
    closed_now: list[DuaQueue] = []
    for queue in result.scalars().all():
        if dua_queue_domain.is_expired(queue.expires_at, now):
            queue.closed = True
            queue.closed_reason = "expired"
            closed_now.append(queue)
    if closed_now:
        await session.flush()
    return closed_now


# ---------------------------------------------------------------------------
# ساخت پنل
# ---------------------------------------------------------------------------


class CreateQueueResult:
    SUCCESS = "success"
    NOT_STARTED = "not_started"
    QUOTA_NOT_COMPLETE = "quota_not_complete"
    OWNER_COOLDOWN = "owner_cooldown"
    # کاربر همین الان یک پنل باز دارد -> پنل جدید ساخته نمی‌شود، فقط وضعیت پنل فعلی نمایش داده می‌شود.
    ACTIVE_QUEUE_EXISTS = "active_queue_exists"


@dataclass
class CreateQueueOutcome:
    result: str
    queue: DuaQueue | None = None
    dhikr: DhikrDefinition | None = None
    daily_free_dhikr_count: int = 0


async def create_dua_queue(
    session: AsyncSession, user: User, chat_id: int, now: datetime | None = None
) -> CreateQueueOutcome:
    now = now or datetime.now(timezone.utc)

    if user.level < 1:
        # بازی هنوز شروع نشده -> طبق قانون کلی پروژه، بی‌سروصدا نادیده گرفته می‌شود.
        return CreateQueueOutcome(result=CreateQueueResult.NOT_STARTED)

    today_str = dua_queue_domain.tehran_date_str(now)
    today_count = user.daily_free_dhikr_count if user.daily_free_dhikr_date == today_str else 0
    if today_count < dua_queue_domain.DAILY_FREE_DHIKR_REQUIRED:
        return CreateQueueOutcome(
            result=CreateQueueResult.QUOTA_NOT_COMPLETE, daily_free_dhikr_count=today_count
        )

    # اگر پنل باز دارد (هنوز ۵ نفر پاسخ نداده‌اند و ۱۲ ساعت نگذشته)، پیام محدودیت ۲۴ ساعته
    # نباید بیاید؛ فقط همان پنل نمایش داده می‌شود. محدودیت ۲۴ ساعته بعد از بسته شدن پنل اعمال می‌شود.
    open_queue = await _find_open_queue(session, user.id, now)
    if open_queue is not None:
        return CreateQueueOutcome(result=CreateQueueResult.ACTIVE_QUEUE_EXISTS, queue=open_queue)

    if await _has_recent_queue(session, user.id, now):
        return CreateQueueOutcome(result=CreateQueueResult.OWNER_COOLDOWN)

    dhikr = random.choice(DUA_QUEUE_DHIKR_LIST)

    queue = DuaQueue(
        owner_user_id=user.id,
        chat_id=chat_id,
        created_at=now,
        expires_at=dua_queue_domain.compute_expiry(now),
        answers_count=0,
        closed=False,
        dhikr_key=dhikr.key,
    )
    session.add(queue)
    await session.flush()

    return CreateQueueOutcome(result=CreateQueueResult.SUCCESS, queue=queue, dhikr=dhikr)


# ---------------------------------------------------------------------------
# پیدا کردن پنل از روی پیام ریپلای‌شده
# ---------------------------------------------------------------------------


async def find_queue_by_panel_message(
    session: AsyncSession, chat_id: int, message_id: int
) -> DuaQueue | None:
    result = await session.execute(
        select(DuaQueue).where(DuaQueue.chat_id == chat_id, DuaQueue.message_id == message_id)
    )
    queue = result.scalar_one_or_none()
    if queue is not None:
        return queue
    # ریپلای روی پیام وضعیتِ اضافه (وقتی صاحب پنل دوباره «التماس دعا» زده) هم پاسخ به پنل است.
    extra = await session.execute(
        select(DuaQueue)
        .join(DuaQueueExtraMessage, DuaQueueExtraMessage.queue_id == DuaQueue.id)
        .where(DuaQueueExtraMessage.chat_id == chat_id, DuaQueueExtraMessage.message_id == message_id)
    )
    return extra.scalar_one_or_none()


async def register_extra_panel_message(
    session: AsyncSession, queue_id: int, chat_id: int, message_id: int
) -> None:
    session.add(DuaQueueExtraMessage(queue_id=queue_id, chat_id=chat_id, message_id=message_id))
    await session.flush()


# ---------------------------------------------------------------------------
# پاسخ به پنل (ریپلای با متن ذکر)
# ---------------------------------------------------------------------------


class AnswerQueueResult:
    SUCCESS = "success"
    NOT_FOUND = "not_found"  # پنل نیست / پنل قدیمی (بدون ذکر) -> نادیده گرفته می‌شود
    TEXT_MISMATCH = "text_mismatch"  # متن ریپلای همان ذکر پنل نیست -> نادیده گرفته می‌شود
    CLOSED = "closed"
    OWNER_CANNOT_ANSWER = "owner_cannot_answer"
    NOT_STARTED = "not_started"
    ALREADY_ANSWERED = "already_answered"
    DHIKR_FAILED = "dhikr_failed"  # process_activity چیزی غیر از SUCCESS برگرداند (cooldown و ...)


@dataclass
class AnswerQueueOutcome:
    result: str
    queue: DuaQueue | None = None
    activity_outcome: ActivityOutcome | None = None
    owner_noor_current: int | None = None
    now_closed: bool = False
    # اطلاعات صاحب پنل برای بازسازی متن پنل و پیام بونوس (بدون کوئری اضافه در handler)
    owner_telegram_id: int | None = None
    owner_first_name: str | None = None
    owner_reward_total: int = 0  # مجموع نوری که همین پاسخ به صاحب پنل داد (شامل بونوس)
    completion_bonus_paid: bool = False


async def answer_dua_queue(
    session: AsyncSession,
    *,
    queue: DuaQueue,
    update_id: int,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    raw_text: str,
    now: datetime | None = None,
) -> AnswerQueueOutcome:
    """
    پاسخ به پنل با ریپلای. `queue` باید داخل همین session/تراکنش خوانده شده باشد
    (find_queue_by_panel_message)، و فراخوان باید متن را پیش‌تر با ذکر پنل چک کرده باشد یا
    اینجا TEXT_MISMATCH برگردانده می‌شود.
    """
    now = now or datetime.now(timezone.utc)

    dhikr = get_queue_dhikr(queue)
    if dhikr is None:
        return AnswerQueueOutcome(result=AnswerQueueResult.NOT_FOUND)

    normalized = normalize_text(raw_text)
    if normalized not in {normalize_text(t) for t in dhikr.canonical_texts}:
        return AnswerQueueOutcome(result=AnswerQueueResult.TEXT_MISMATCH, queue=queue)

    if not dua_queue_domain.is_queue_open(
        closed=queue.closed, answers_count=queue.answers_count, expires_at=queue.expires_at, now=now
    ):
        if not queue.closed:
            queue.closed = True
            queue.closed_reason = (
                "expired" if dua_queue_domain.is_expired(queue.expires_at, now) else "max_answers"
            )
            await session.flush()
        return AnswerQueueOutcome(result=AnswerQueueResult.CLOSED, queue=queue)

    responder = await get_or_create_user(session, telegram_id, username, first_name)

    if responder.id == queue.owner_user_id:
        return AnswerQueueOutcome(result=AnswerQueueResult.OWNER_CANNOT_ANSWER, queue=queue)

    if responder.level < 1:
        return AnswerQueueOutcome(result=AnswerQueueResult.NOT_STARTED, queue=queue)

    existing = await session.execute(
        select(DuaQueueAnswer.id).where(
            DuaQueueAnswer.queue_id == queue.id, DuaQueueAnswer.responder_user_id == responder.id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return AnswerQueueOutcome(result=AnswerQueueResult.ALREADY_ANSWERED, queue=queue)

    # --- مسیر اصلی ثبت فعالیت (بدون سیستم موازی) ---
    activity_outcome = await process_activity(
        session,
        update_id=update_id,
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        chat_id=queue.chat_id,
        raw_text=raw_text,
        now=now,
        forced_dhikr=dhikr,
    )

    if activity_outcome.status != OutcomeStatus.SUCCESS:
        # اگر ذکر به هر دلیل ثبت نشد (cooldown، duplicate update و ...)، پاسخ پنل هم ثبت نمی‌شود.
        return AnswerQueueOutcome(
            result=AnswerQueueResult.DHIKR_FAILED, queue=queue, activity_outcome=activity_outcome
        )

    session.add(DuaQueueAnswer(queue_id=queue.id, responder_user_id=responder.id, created_at=now))
    queue.answers_count += 1

    owner = await session.get(User, queue.owner_user_id)
    owner_reward = dua_queue_domain.QUEUE_OWNER_REWARD_PER_ANSWER

    now_closed = False
    bonus_paid = False
    if queue.answers_count >= dua_queue_domain.QUEUE_MAX_ANSWERS:
        queue.closed = True
        queue.closed_reason = "max_answers"
        now_closed = True
        # چون پنل با همین پاسخ بسته می‌شود، بونوس دقیقاً یک‌بار پرداخت می‌شود.
        owner_reward += dua_queue_domain.QUEUE_OWNER_COMPLETION_BONUS
        bonus_paid = True

    owner.noor_current += owner_reward
    owner.noor_total_earned += owner_reward

    await session.flush()

    return AnswerQueueOutcome(
        result=AnswerQueueResult.SUCCESS,
        queue=queue,
        activity_outcome=activity_outcome,
        owner_noor_current=owner.noor_current,
        now_closed=now_closed,
        owner_telegram_id=owner.telegram_id,
        owner_first_name=owner.first_name,
        owner_reward_total=owner_reward,
        completion_bonus_paid=bonus_paid,
    )
