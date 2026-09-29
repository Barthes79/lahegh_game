"""
موتور اصلی پردازش یک فعالیت (پیام گروه) — دقیقاً طبق ترتیب ۱۳ مرحله‌ای بخش ۱۰ سند.

این تابع باید همیشه داخل یک تراکنش دیتابیسی صدا زده شود (session.begin())، و پیش از هر
منطق کسب‌وکاری، update_id تلگرام را claim می‌کند (بخش ۲۰: anti-exploit).

خروجی یک ActivityOutcome است که تمام اطلاعات لازم برای ساختن پیام(های) پاسخ را دارد؛
ارسال واقعی پیام به تلگرام بر عهده‌ی handler است (بعد از commit موفق تراکنش).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Chest, DhikrUnlock, User
from bot.domain import chest as chest_domain
from bot.domain import dhikr_circle as circle_domain
from bot.domain import dua_queue as dua_queue_domain
from bot.domain.cooldown import get_salawat_cooldown_seconds, remaining_seconds
from bot.domain.dhikr_data import CIRCLE_DISPLAY_DHIKR_KEYS, DHIKR_BY_KEY, DhikrDefinition
from bot.domain.milestones import (
    MILESTONE_BANK_AZKAR,
    MILESTONE_LEVEL_UP,
    MILESTONE_LEVEL_UP_3,
    MILESTONE_NAMEH_AMAL,
    MILESTONE_TASBIH,
)
from bot.services.job_service import ProductionProgress, apply_production_dhikr
from bot.domain.salawat_data import (
    LEVEL_1_REQUIRED_SALAWAT,
    LEVEL_2_REQUIRED_SALAWAT,
    LEVEL_3_REQUIRED_SALAWAT,
    get_level_required_salawat,
    SALAWAT_NOOR_REWARD,
    SALAWAT_PROGRESS_STEP,
)
from bot.domain.tasbih_data import get_dhikr_cooldown_for_level
from bot.domain.validator import ActivityKind, ClassificationResult, classify_message
from bot.services.idempotency import try_claim_update
from bot.services.dhikr_circle_service import (
    CircleActivityResult,
    apply_circle_dhikr,
    get_or_assign_display_dhikr,
)
from bot.services.user_service import get_or_create_user

# احتمال نمایش پیام کامل به‌جای فقط reaction (بخش ۹: ۳۳٪ پیام کامل / ۶۷٪ فقط reaction)
FULL_MESSAGE_PROBABILITY = 0.33
CIRCLE_FULL_MESSAGE_PROBABILITY = 0.30

class OutcomeStatus:
    DUPLICATE_UPDATE = "duplicate_update"
    UNRELATED = "unrelated"
    INVALID_SILENT = "invalid_silent"
    LOCKED_DHIKR = "locked_dhikr"
    COOLDOWN = "cooldown"
    CIRCLE_DAILY_LIMIT = "circle_daily_limit"
    JAILED = "jailed"
    SUCCESS = "success"


@dataclass
class ActivityOutcome:
    status: str
    activity_kind: ActivityKind | None = None
    dhikr_def: DhikrDefinition | None = None

    cooldown_remaining_seconds: int | None = None
    jail_remaining_seconds: int = 0  # فقط وقتی status == JAILED

    # cooldown کامل (ثانیه) تا فعالیت بعدی از همین نوع، بلافاصله بعد از یک ثبت موفق —
    # برای خط «⏳ صلوات/ذکر بعدی» در پیام موفقیت عادی استفاده می‌شود.
    next_cooldown_seconds: int = 0

    noor_reward: int = 0
    noor_current: int = 0
    level_progress: int = 0
    level_progress_total: int = LEVEL_1_REQUIRED_SALAWAT
    is_first_activity: bool = False
    use_full_message: bool = True
    needs_reaction_explanation: bool = False

    # اصلاحات نهایی: milestone_kind یکی از "bank_azkar"/"nameh_amal"/"tasbih"/"level_up" یا
    # None است. وقتی مقدار دارد، handler باید یک پیام کامل واحد (فعالیت+Milestone) بسازد
    # و رندر جداگانه‌ی نتیجه‌ی فعالیت/reaction/PV را برای همین فعالیت انجام ندهد.
    milestone_kind: str | None = None
    level_up_triggered: bool = False

    chest: Chest | None = None
    chest_is_first_ever: bool = False

    # --- Level 2: حلقه ذکر --- (فقط برای فعالیت‌های DHIKR کاربرانی که عضو یک حلقه‌اند)
    circle_daily_count: int = 0
    circle_daily_target: int = 0
    circle_just_completed_today: bool = False
    # هرکدام (telegram_id, username, first_name) — برای رندر پیام milestone بدون کوئری اضافه
    circle_milestone_winners: list[tuple[int, str | None, str | None]] = field(default_factory=list)
    is_circle_dhikr: bool = False

    # --- Level 3: تولید شغل --- (فقط برای ذکرهای عادی کاربری که تولید فعال دارد)
    production: ProductionProgress | None = None


async def _is_dhikr_unlocked(session: AsyncSession, user: User, dhikr: DhikrDefinition) -> bool:
    if dhikr.unlock_cost == 0:
        return True
    result = await session.execute(
        select(DhikrUnlock).where(
            DhikrUnlock.user_id == user.id, DhikrUnlock.dhikr_key == dhikr.key
        )
    )
    return result.scalar_one_or_none() is not None


def _pick_message_style() -> bool:
    """True یعنی پیام کامل (۳۳٪)، False یعنی فقط reaction (۶۷٪)."""
    return random.random() < FULL_MESSAGE_PROBABILITY


async def process_activity(
    session: AsyncSession,
    *,
    update_id: int,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    chat_id: int,
    raw_text: str,
    now: datetime | None = None,
    forced_dhikr: DhikrDefinition | None = None,
) -> ActivityOutcome:
    """
    forced_dhikr (Level 2 — التماس دعا): اگر داده شود، متن پیام classify نمی‌شود و همین ذکر
    مستقیماً از مسیر عادی ثبت ذکر (cooldown، idempotency، سهمیه‌ی روزانه) رد می‌شود. فراخوان
    (dua_queue_service) مسئول تطبیق متن پیام با ذکر پنل است. این ذکرها عمداً داخل DHIKR_LIST
    نیستند تا بیرون از پنل قابل ثبت نباشند.

    توجه (اصلاحات نهایی، بند ۲): این تابع فقط باید برای پیام‌های *داخل گروه* صدا زده شود.
    فراخوان (handler) مسئول است که پیام‌های PV را اصلاً به این تابع نرساند، چون فعالیت در
    PV نباید ثبت شود، نور بدهد، Progress را تغییر دهد یا cooldown/صندوقچه را تحت تأثیر قرار دهد.
    """
    now = now or datetime.now(timezone.utc)

    claimed = await try_claim_update(session, update_id)
    if not claimed:
        return ActivityOutcome(status=OutcomeStatus.DUPLICATE_UPDATE)

    if forced_dhikr is not None:
        classification = ClassificationResult(ActivityKind.DHIKR, dhikr_key=forced_dhikr.key)
    else:
        classification = classify_message(raw_text)

    if classification.kind == ActivityKind.UNRELATED:
        return ActivityOutcome(status=OutcomeStatus.UNRELATED)

    user = await get_or_create_user(session, telegram_id, username, first_name)

    # Level 3 — بانک: مادامی که کاربر به‌خاطر ندادن بدهی در زندان است، صلوات/ذکرش
    # (چه عادی چه حلقه) ثبت نمی‌شود؛ بدون هیچ اثری روی cooldown یا سهمیه‌ها.
    from bot.services.bank_service import jail_remaining_seconds as _jail_remaining

    remaining = _jail_remaining(user, now)
    if remaining > 0:
        return ActivityOutcome(status=OutcomeStatus.JAILED, jail_remaining_seconds=remaining)

    # حلقه ذکر یک قابلیت مستقلِ Level 2 است. طبق قوانین حلقه، داشتن Level 2
    # برای ثبت ذکر حلقه کافی است و نباید وابسته به game_started باشد.
    # در غیر این صورت کاربری که Level 2 شده ولی فلگ game_started او قدیمی/False است،
    # پیام ذکر حلقه را قبل از رسیدن به مسیر ثبت از دست می‌دهد.
    is_circle_member = user.active_circle_id is not None and user.level >= 2
    if (
        not user.game_started
        and classification.kind != ActivityKind.SALAWAT
        and not is_circle_member
    ):
        return ActivityOutcome(status=OutcomeStatus.UNRELATED)

    if classification.kind == ActivityKind.INVALID_ATTEMPT:
        # طبق درخواست صریح کاربر: هیچ‌وقت پیام هشدار «متن واردشده معتبر نیست» نشان داده
        # نشود — چه در cooldown باشد چه نباشد، یک تلاش نامعتبر (متن اضافه/چند فعالیت/
        # غلط املایی و ...) همیشه کاملاً بی‌پاسخ می‌ماند.
        return ActivityOutcome(status=OutcomeStatus.INVALID_SILENT)

    if classification.kind == ActivityKind.SALAWAT:
        is_first_activity = not user.game_started

        if not is_first_activity:
            prior_cooldown = get_salawat_cooldown_seconds(max(user.salawat_count - 1, 0))
            remaining = remaining_seconds(user.last_salawat_at, prior_cooldown, now)
            if remaining > 0:
                return ActivityOutcome(
                    status=OutcomeStatus.COOLDOWN,
                    activity_kind=ActivityKind.SALAWAT,
                    cooldown_remaining_seconds=remaining,
                )

        return await _register_salawat(
            session, user, is_first_activity=is_first_activity, now=now, chat_id=chat_id
        )

    dhikr = forced_dhikr if forced_dhikr is not None else DHIKR_BY_KEY[classification.dhikr_key]

    # ذکر ویژه‌ی «حلقه ذکر» فقط در صورتی ثبت می‌شود که دقیقاً همان ذکرِ فعلی
    # اختصاص‌یافته به کاربر باشد. این کار جلوی دریافت نور با گفتن یکی از ۵ ذکر
    # ویژه‌ی دیگر را می‌گیرد و در عین حال خودِ ذکر نمایش‌داده‌شده را مثل یک
    # فعالیت واقعی وارد همان مسیر ثبت ذکر می‌کند.
    if dhikr.key in CIRCLE_DISPLAY_DHIKR_KEYS:
        # این ذکر وقتی کاربر عضو حلقه است، «ذکر حلقه» محسوب می‌شود.
        # اگر کاربر عضو حلقه نیست، رفتار عادی ذکر حفظ می‌شود.
        user_is_in_circle = user.active_circle_id is not None
        if user_is_in_circle:
            assigned_dhikr = await get_or_assign_display_dhikr(session, user, now=now)
            if dhikr.key != assigned_dhikr.key:
                return ActivityOutcome(status=OutcomeStatus.INVALID_SILENT)

            # سقف سخت روزانه: هر عضو فقط ۱۰ بار می‌تواند «ذکر حلقه» را ثبت کند.
            # این بررسی قبل از پرداخت نور/افزایش شمارنده انجام می‌شود.
            from bot.services.dhikr_circle_service import get_circle_daily_count, expire_expired_circles
            await expire_expired_circles(session, now)
            if user.active_circle_id is None:
                return ActivityOutcome(status=OutcomeStatus.UNRELATED)
            circle_daily_count = await get_circle_daily_count(session, user, now=now)
            if circle_daily_count >= circle_domain.CIRCLE_DAILY_TARGET:
                return ActivityOutcome(status=OutcomeStatus.CIRCLE_DAILY_LIMIT)

    # اصلاحات نهایی («ذکر قبل از باز شدن بانک»): قبل از رسیدن کاربر به صلوات سوم (باز شدن
    # بانک اذکار)، هر ذکر پولی/قفل (غیر از الحمدلله رایگان) باید کاملاً بی‌پاسخ بماند —
    # نه پیام قفل، نه ری‌اکشن، نه نور. الحمدلله (unlock_cost=0) از این قاعده مستثناست چون
    # از همان صلوات اول معرفی و قابل‌استفاده است.
    if dhikr.unlock_cost > 0 and not user.bank_azkar_unlocked:
        return ActivityOutcome(status=OutcomeStatus.INVALID_SILENT)

    unlocked = await _is_dhikr_unlocked(session, user, dhikr)
    if not unlocked:
        return ActivityOutcome(status=OutcomeStatus.LOCKED_DHIKR, dhikr_def=dhikr)

    # ذکرهای ویژه‌ی «حلقه ذکر» یک کولداون کاملاً مستقل و کوتاه دارند (بخش تست سریع)،
    # جدا از کولداون معمول ذکر (که بر اساس سطح تسبیح تعیین می‌شود).
    if dhikr.key in CIRCLE_DISPLAY_DHIKR_KEYS:
        remaining = remaining_seconds(
            user.last_circle_dhikr_at, circle_domain.CIRCLE_DHIKR_COOLDOWN_SECONDS, now
        )
    else:
        dhikr_cooldown = user.last_dhikr_cooldown_seconds or get_dhikr_cooldown_for_level(user.tasbih_level)
        remaining = remaining_seconds(user.last_dhikr_at, dhikr_cooldown, now)
    if remaining > 0:
        return ActivityOutcome(
            status=OutcomeStatus.COOLDOWN,
            activity_kind=ActivityKind.DHIKR,
            cooldown_remaining_seconds=remaining,
        )

    return await _register_dhikr(
        session, user, dhikr, now=now, chat_id=chat_id, is_dua_queue_answer=forced_dhikr is not None
    )


async def _apply_common_after_registration(
    session: AsyncSession, user: User, *, now: datetime, chat_id: int, noor_reward: int
) -> None:
    user.noor_current += noor_reward
    user.noor_total_earned += noor_reward
    user.total_activities += 1
    user.last_activity_at = now
    user.active_chat_id = chat_id
    await session.flush()


async def _register_salawat(
    session: AsyncSession, user: User, *, is_first_activity: bool, now: datetime, chat_id: int
) -> ActivityOutcome:
    outcome = ActivityOutcome(
        status=OutcomeStatus.SUCCESS,
        activity_kind=ActivityKind.SALAWAT,
        noor_reward=SALAWAT_NOOR_REWARD,
        is_first_activity=is_first_activity,
    )

    if is_first_activity:
        user.game_started = True
        user.game_started_at = now
        user.level = 1

    user.last_salawat_at = now
    user.salawat_count += 1

    await _apply_common_after_registration(
        session, user, now=now, chat_id=chat_id, noor_reward=SALAWAT_NOOR_REWARD
    )

    if user.level == 1:
        # صلوات ۱ تا ۱۲ فقط سطح ۱ را کامل می‌کنند؛ ۱۲/۱۲ هنوز سطح ۲ نیست.
        if user.salawat_count <= LEVEL_1_REQUIRED_SALAWAT:
            user.level_progress = min(
                LEVEL_1_REQUIRED_SALAWAT, user.level_progress + SALAWAT_PROGRESS_STEP
            )

        if user.level_progress == MILESTONE_BANK_AZKAR and not user.bank_azkar_unlocked:
            user.bank_azkar_unlocked = True
            outcome.milestone_kind = "bank_azkar"

        if user.level_progress == MILESTONE_NAMEH_AMAL and not user.nameh_amal_unlocked:
            user.nameh_amal_unlocked = True
            outcome.milestone_kind = "nameh_amal"

        if user.level_progress == MILESTONE_TASBIH and not user.tasbih_unlocked:
            user.tasbih_unlocked = True
            user.tasbih_level = 1
            outcome.milestone_kind = "tasbih"

        # صلوات سیزدهم اولین صلوات سطح ۲ است و باید 1/24 نمایش داده شود.
        if user.salawat_count == MILESTONE_LEVEL_UP and user.level == 1:
            user.level = 2
            user.level_progress = 1
            outcome.level_up_triggered = True
            outcome.milestone_kind = "level_up"

    elif user.level == 2:
        if user.level_progress >= LEVEL_2_REQUIRED_SALAWAT:
            # پیشرفت سطح ۲ کامل (۲۴/۲۴) بوده و کاربر صلوات بعدی را گفته: ورود به سطح ۳
            # (مثل سطح ۱: صلوات بعد از ۱۲/۱۲ اولین صلوات سطح جدید است و 1/N نشان داده می‌شود).
            user.level = 3
            user.level_progress = 1
            outcome.level_up_triggered = True
            outcome.milestone_kind = MILESTONE_LEVEL_UP_3
        else:
            # بعد از صلوات سیزدهم، صلوات‌های بعدی پیشرفت سطح ۲ را از 1/24 ادامه می‌دهند.
            user.level_progress = min(
                LEVEL_2_REQUIRED_SALAWAT, user.level_progress + SALAWAT_PROGRESS_STEP
            )

    elif user.level == 3:
        user.level_progress = min(
            LEVEL_3_REQUIRED_SALAWAT, user.level_progress + SALAWAT_PROGRESS_STEP
        )

    await session.flush()

    outcome.noor_current = user.noor_current
    outcome.level_progress = user.level_progress
    outcome.level_progress_total = get_level_required_salawat(user.level)
    outcome.next_cooldown_seconds = get_salawat_cooldown_seconds(user.salawat_count - 1)

    if outcome.milestone_kind is not None:
        # اصلاحات نهایی: صلوات‌های ۳/۶/۹/۱۲ همیشه یک پیام کامل واحد می‌گیرند
        # (مستقل از قانون ۶۷٪/۳۳٪)، و نیازی به توضیح reaction هم ندارند.
        outcome.use_full_message = True
    else:
        outcome.use_full_message = True if is_first_activity else _pick_message_style()
        if not is_first_activity and not outcome.use_full_message and not user.reaction_explained:
            user.reaction_explained = True
            outcome.needs_reaction_explanation = True

    await _maybe_create_chest(session, user, outcome, now=now)
    return outcome


async def _register_dhikr(
    session: AsyncSession,
    user: User,
    dhikr: DhikrDefinition,
    *,
    now: datetime,
    chat_id: int,
    is_dua_queue_answer: bool = False,
) -> ActivityOutcome:
    outcome = ActivityOutcome(
        status=OutcomeStatus.SUCCESS,
        activity_kind=ActivityKind.DHIKR,
        dhikr_def=dhikr,
        noor_reward=dhikr.noor_reward,
        is_circle_dhikr=(dhikr.key in CIRCLE_DISPLAY_DHIKR_KEYS and user.active_circle_id is not None),
    )

    if dhikr.key in CIRCLE_DISPLAY_DHIKR_KEYS:
        user.last_circle_dhikr_at = now
        next_cooldown_seconds = circle_domain.CIRCLE_DHIKR_COOLDOWN_SECONDS
    else:
        user.last_dhikr_at = now
        user.last_dhikr_cooldown_seconds = (
            dhikr.cooldown_seconds
            if dhikr.cooldown_seconds is not None
            else get_dhikr_cooldown_for_level(user.tasbih_level)
        )
        next_cooldown_seconds = user.last_dhikr_cooldown_seconds
    user.dhikr_count += 1

    await _apply_common_after_registration(
        session, user, now=now, chat_id=chat_id, noor_reward=dhikr.noor_reward
    )

    # --- Level 2: سهمیه‌ی روزانه‌ی ذکر (شرط باز شدن پنل «التماس دعا») ---
    # فقط اینجا (بعد از ثبت موفق ذکر) افزایش پیدا می‌کند؛ cooldown/قفل/نامعتبر هرگز به این خط
    # نمی‌رسند. طبق تصمیم طراح، «ذکر حلقه» (وقتی کاربر عضو حلقه است) و صلوات حساب نمی‌شوند.
    dua_queue_just_unlocked = False
    if not outcome.is_circle_dhikr:
        today_str = dua_queue_domain.tehran_date_str(now)
        if user.daily_free_dhikr_date != today_str:
            user.daily_free_dhikr_date = today_str
            user.daily_free_dhikr_count = 0
        user.daily_free_dhikr_count += 1
        dua_queue_just_unlocked = (
            user.daily_free_dhikr_count == dua_queue_domain.DAILY_FREE_DHIKR_REQUIRED
        )

    # --- Level 2: حلقه ذکر --- اگر کاربر عضو یک حلقه است، روی همین ذکرِ از قبل موفق
    # پیشرفت روزانه/bonus/milestone اعمال می‌شود. سیستم ثبت ذکر موازی ساخته نشده؛
    # این فقط یک افزوده‌ی جانبی روی همان فعالیتی است که بالا ثبت شد.
    # ذکر پاسخ به پنل «التماس دعا» ذکر حلقه نیست و روی پیشرفت حلقه اثری ندارد.
    if is_dua_queue_answer:
        circle_result = CircleActivityResult(applied=False)
    else:
        circle_result = await apply_circle_dhikr(session, user, now=now)
    if circle_result.applied and circle_result.bonus_noor:
        user.noor_current += circle_result.bonus_noor
        user.noor_total_earned += circle_result.bonus_noor
        outcome.noor_reward += circle_result.bonus_noor

    outcome.circle_daily_count = circle_result.daily_count
    outcome.circle_daily_target = circle_result.daily_target
    outcome.circle_just_completed_today = circle_result.just_completed_today
    if circle_result.milestone is not None:
        outcome.circle_milestone_winners = [
            (u.telegram_id, u.username, u.first_name) for u in circle_result.milestone.winners
        ]

    # --- Level 3: پیشرفت تولید شغل --- فقط ذکر عادیِ کاربر (نه ذکر حلقه، نه پاسخ به التماس دعا).
    # روی همان ذکرِ از قبل موفق اعمال می‌شود؛ سیستم ثبت ذکر موازی ساخته نشده.
    if (
        not outcome.is_circle_dhikr
        and not is_dua_queue_answer
        and dhikr.key not in CIRCLE_DISPLAY_DHIKR_KEYS
    ):
        outcome.production = await apply_production_dhikr(session, user)

    outcome.noor_current = user.noor_current
    outcome.next_cooldown_seconds = next_cooldown_seconds

    if outcome.is_circle_dhikr:
        # حلقه ذکر: ۳۰٪ پیام کامل در گروه، ۷۰٪ واکنش + نتیجه در PV.
        outcome.use_full_message = random.random() < CIRCLE_FULL_MESSAGE_PROBABILITY
        outcome.needs_reaction_explanation = False
    elif dua_queue_just_unlocked:
        # طبق قانون کلی پروژه: باز شدن یک قابلیت جدید همیشه پیام کامل می‌گیرد
        # (مستقل از قانون ۶۷٪/۳۳٪ reaction)، دقیقاً مثل milestoneهای صلوات.
        outcome.milestone_kind = "dua_queue_unlocked"
        outcome.use_full_message = True
    else:
        outcome.use_full_message = _pick_message_style()
        if not outcome.use_full_message and not user.reaction_explained:
            user.reaction_explained = True
            outcome.needs_reaction_explanation = True

    await session.flush()
    await _maybe_create_chest(session, user, outcome, now=now)
    return outcome


async def _maybe_create_chest(
    session: AsyncSession, user: User, outcome: ActivityOutcome, *, now: datetime
) -> None:
    if not chest_domain.can_create_new_chest(user.last_chest_created_at, now):
        return
    if not chest_domain.roll_chest_found():
        return

    chest = Chest(
        user_id=user.id,
        chat_id=user.active_chat_id or 0,
        created_at=now,
        expires_at=chest_domain.compute_expiry(now),
        opened=False,
    )
    session.add(chest)

    outcome.chest_is_first_ever = user.chest_count == 0
    user.chest_count += 1
    user.last_chest_created_at = now

    await session.flush()
    outcome.chest = chest
