"""
هندلر پنل «حلقه ذکر» (Level 2).

دعوت فقط با روش Reply انجام می‌شود:
  روی پیام شخص موردنظر ریپلای کن و بنویس «حلقه ذکر»
سپس در PV آن شخص، دو دکمه «✅ قبول دعوت» / «❌ رد دعوت» می‌آید.

پنل فقط در گروه نمایش داده می‌شود؛ در PV کاربر «حلقه ذکر» بی‌صدا نادیده گرفته می‌شود.

بعد از قبول دعوت هم در PV پنل فرستاده نمی‌شود؛ فقط پیام تأیید + راهنما.

سازنده‌ی حلقه در پنل با 👑 و بقیه با 🟢 نمایش داده می‌شوند.

پنل owner-scoped است: callback_data شامل owner_id است تا کلیک غریبه‌ها روی پنل دیگران بی‌اثر باشد.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from aiogram import Router
from aiogram.enums import ChatType, ParseMode
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.database.engine import async_session_factory
from bot.database.models import DhikrCircle, User as UserModel
from bot.domain import dhikr_circle as circle_domain
from bot.domain.dua_queue import tehran_date_str
from bot.domain.milestones import COMMAND_DHIKR_CIRCLE
from bot.domain.normalization import normalize_text
from bot.keyboards.inline import (
    circle_invite_confirmation_keyboard,
    circle_leave_confirm_keyboard,
    circle_main_keyboard,
    circle_no_circle_keyboard,
)
from bot.services.dhikr_circle_service import (
    ClaimPersonalRewardResult,
    CreateCircleResult,
    JoinCircleResult,
    LeaveCircleResult,
    claim_circle_personal_reward,
    create_circle,
    get_circle_with_members,
    get_or_assign_display_dhikr,
    join_circle,
    leave_circle,
    expire_expired_circles,
)
from bot.services.reminder_service import build_user_mention
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id
from bot.texts import messages as texts

logger = logging.getLogger(__name__)

router = Router(name="dhikr_circle")

# پیام پنل بازِ هر کاربر در این runtime؛ بدون migration جدید.
# key = telegram_id -> (chat_id, message_id)
_CIRCLE_PANEL_MESSAGES: dict[int, tuple[int, int]] = {}


# ---------------------------------------------------------------------------
# ابزارهای کوچک
# ---------------------------------------------------------------------------


def _member_label(user: UserModel | None) -> str:
    if user is None:
        return "کاربر"
    if user.username:
        return f"@{user.username}"
    if user.first_name:
        return user.first_name
    return "کاربر"


def _hours_left(unlock_at: datetime) -> int:
    now = datetime.now(timezone.utc)
    if unlock_at.tzinfo is None:
        unlock_at = unlock_at.replace(tzinfo=timezone.utc)
    return max(1, math.ceil((unlock_at - now).total_seconds() / 3600))


async def _users_by_id(session, user_ids: list[int]) -> dict[int, UserModel]:
    if not user_ids:
        return {}
    result = await session.execute(select(UserModel).where(UserModel.id.in_(user_ids)))
    return {u.id: u for u in result.scalars().all()}


# ---------------------------------------------------------------------------
# ساخت داده پنل
# ---------------------------------------------------------------------------


async def _circle_panel_data(session, user: UserModel):
    """
    داده‌ی موردنیاز پنل حلقه.

    members_progress: لیست چهارتایی (label, count, target, is_creator)
    که is_creator یعنی همین عضو، سازنده‌ی حلقه است (برای نمایش 👑).
    """
    circle, members = await get_circle_with_members(session, user.active_circle_id)
    if circle is None:
        return None

    users_by_id = await _users_by_id(session, [m.user_id for m in members])
    # سهم حلقه بر اساس پنجره‌ی ۲۴ ساعته‌ی کاربر محاسبه می‌شود، نه نیمه‌شب تهران.
    # daily_date در مدل قدیمی برای تاریخ روزانه بود و با منطق جدید 24h باعث می‌شد
    # نوار همیشه 0/10 نمایش داده شود.
    now = datetime.now(timezone.utc)
    today_str = tehran_date_str(now)

    members_progress = []
    completed_count = 0
    my_count = 0
    for member in members:
        member_user = users_by_id.get(member.user_id)
        count = 0
        if member_user is not None:
            started = member_user.circle_daily_dhikr_started_at
            if started is not None and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if (
                started is not None
                and now < started + circle_domain.CIRCLE_USER_QUOTA_WINDOW
            ):
                count = min(
                    member_user.circle_daily_dhikr_count or 0,
                    circle_domain.CIRCLE_DAILY_TARGET,
                )
        count = min(count, circle_domain.CIRCLE_DAILY_TARGET)
        if count >= circle_domain.CIRCLE_DAILY_TARGET:
            completed_count += 1
        if member.user_id == user.id:
            my_count = count
        members_progress.append(
            (
                _member_label(users_by_id.get(member.user_id)),
                count,
                circle_domain.CIRCLE_DAILY_TARGET,
                member.user_id == circle.creator_user_id,
            )
        )

    personal_reward_paid = user.circle_personal_reward_date == today_str
    # ذکر روزانه‌ی حلقه مستقیماً داخل همین پنل نمایش داده می‌شود؛
    # پیام/پنل جداگانه‌ای برای آن ساخته نمی‌شود.
    display_dhikr = await get_or_assign_display_dhikr(session, user)
    return {
        "circle": circle,
        "display_dhikr": display_dhikr,
        "members_progress": members_progress,
        "my_count": my_count,
        "today": today_str,
        "completed_count": completed_count,
        "personal_reward_paid": personal_reward_paid,
        "can_claim_reward": (not personal_reward_paid) and my_count >= circle_domain.CIRCLE_DAILY_TARGET,
        "group_reward_paid": circle.milestone_paid_date == today_str,
    }


async def _send_circle_panel(message_or_callback, user_id: int, *, edit: bool = False) -> bool:
    """
    ساخت و ارسال/ویرایش پنل حلقه ذکر.

    متن پنل با HTML ارسال می‌شود تا ذکر امروز داخل <code>...</code>
    قرار بگیرد و تلگرام برای آن امکان کپی مستقیم نمایش دهد.
    """
    try:
        async with async_session_factory() as session:
            async with session.begin():
                user = await get_user_by_telegram_id(session, user_id)
                if user is None or user.active_circle_id is None:
                    return False
                data = await _circle_panel_data(session, user)
                if data is None:
                    return False

        text = texts.circle_main_panel_text(
            circle_name=data["circle"].name,
            display_dhikr=data["display_dhikr"],
            members_progress=data["members_progress"],
            my_count=data["my_count"],
            daily_target=circle_domain.CIRCLE_DAILY_TARGET,
            personal_reward_paid=data["personal_reward_paid"],
            group_completed_count=data["completed_count"],
            group_target=circle_domain.CIRCLE_MILESTONE_MIN_MEMBERS,
            group_reward_paid=data["group_reward_paid"],
        )
        markup = circle_main_keyboard(user_id, can_claim_reward=data["can_claim_reward"])

        if edit:
            await message_or_callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
            _CIRCLE_PANEL_MESSAGES[user_id] = (
                message_or_callback.message.chat.id,
                message_or_callback.message.message_id,
            )
        else:
            sent = await message_or_callback.reply(text, reply_markup=markup, parse_mode="HTML")
            _CIRCLE_PANEL_MESSAGES[user_id] = (sent.chat.id, sent.message_id)
        return True
    except Exception:
        logger.exception("ارسال/ویرایش پنل حلقه ذکر ناموفق بود (user_id=%s)", user_id)
        return False


async def refresh_circle_panels(bot: Bot, actor_telegram_id: int) -> None:
    """
    پنل بازِ حلقه را بعد از ثبت موفق ذکر، برای همه اعضای همان حلقه refresh می‌کند.

    فقط پیام‌های پنلی که در همین runtime شناخته شده‌اند ویرایش می‌شوند؛ اگر ربات
    restart شده باشد، کاربر با بازکردن دوباره «حلقه ذکر» پنل جدیدی در cache خواهد داشت.
    """
    try:
        async with async_session_factory() as session:
            async with session.begin():
                actor = await get_user_by_telegram_id(session, actor_telegram_id)
                if actor is None or actor.active_circle_id is None:
                    return
                circle, members = await get_circle_with_members(session, actor.active_circle_id)
                if circle is None:
                    return
                member_user_ids = []
                for member in members:
                    u = await session.get(UserModel, member.user_id)
                    if u is not None and u.active_circle_id == circle.id:
                        member_user_ids.append(u.telegram_id)

        # خارج از transaction و بعد از commit، پیام‌های Telegram را ویرایش می‌کنیم.
        for telegram_id in member_user_ids:
            target = _CIRCLE_PANEL_MESSAGES.get(telegram_id)
            if target is None:
                continue
            chat_id, message_id = target
            try:
                async with async_session_factory() as session:
                    async with session.begin():
                        user = await get_user_by_telegram_id(session, telegram_id)
                        if user is None or user.active_circle_id != circle.id:
                            continue
                        data = await _circle_panel_data(session, user)

                if data is None:
                    continue
                text = texts.circle_main_panel_text(
                    circle_name=data["circle"].name,
                    display_dhikr=data["display_dhikr"],
                    members_progress=data["members_progress"],
                    my_count=data["my_count"],
                    daily_target=circle_domain.CIRCLE_DAILY_TARGET,
                    personal_reward_paid=data["personal_reward_paid"],
                    group_completed_count=data["completed_count"],
                    group_target=circle_domain.CIRCLE_MILESTONE_MIN_MEMBERS,
                    group_reward_paid=data["group_reward_paid"],
                )
                markup = circle_main_keyboard(
                    telegram_id,
                    can_claim_reward=data["can_claim_reward"],
                )
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML",
                )
            except Exception:
                # ممکن است پیام پنل توسط کاربر/تلگرام حذف شده باشد؛ cache را پاک می‌کنیم.
                _CIRCLE_PANEL_MESSAGES.pop(telegram_id, None)
                logger.debug("refresh پنل حلقه برای %s ناموفق بود", telegram_id, exc_info=True)
    except Exception:
        logger.exception("refresh پنل‌های حلقه ناموفق بود (actor=%s)", actor_telegram_id)


# ---------------------------------------------------------------------------
# دستور «حلقه ذکر» (بدون Reply) — فقط در گروه
# ---------------------------------------------------------------------------


async def create_dhikr_circle_command(message: Message) -> None:
    """
    دستور «حلقه ذکر» در گروه.

    رفتار نهایی:
    - اگر کاربر Level 2+ باشد و هنوز حلقه نداشته باشد، بدون پرسیدن نام،
      یک حلقه با نام پیش‌فرض «حلقه ذکر» برای او ساخته می‌شود.
    - اگر از قبل عضو حلقه باشد، فقط همان پنل را نمایش می‌دهیم.
    - ذکر روزانه داخل خود پنل قرار دارد و پیام جداگانه‌ای برای آن ارسال نمی‌شود.
    """
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if message.from_user is None:
        return

    owner_id = message.from_user.id

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(
                session, owner_id, message.from_user.username, message.from_user.first_name
            )

            if user.level < 2:
                # قابلیت حلقه ذکر از Level 2 در دسترس است.
                return

            if user.active_circle_id is None:
                # نام حلقه عمداً از کاربر پرسیده نمی‌شود.
                # create_circle به‌صورت پیش‌فرض «حلقه ذکر» را انتخاب می‌کند.
                outcome = await create_circle(session, user)

                if outcome.result not in (
                    CreateCircleResult.SUCCESS,
                    CreateCircleResult.ALREADY_IN_CIRCLE,
                ):
                    logger.warning(
                        "ساخت خودکار حلقه برای کاربر %s ناموفق بود: %s",
                        owner_id,
                        outcome.result,
                    )
                    return

    # هر بار که کاربر «حلقه ذکر» را می‌نویسد، یک پنل تازه برایش باز کن.
    # این رفتار عمداً مستقل از پنل قبلی/کش است تا کاربر بتواند هر زمان خواست
    # دوباره پنل حلقه را باز کند.
    sent = await _send_circle_panel(message, owner_id, edit=False)
    if not sent:
        logger.warning("پنل حلقه برای کاربر %s ارسال نشد", owner_id)
        # اگر ارسال پنل به دلیل یک پیام/کش قدیمی یا خطای تلگرام شکست خورد،
        # کش محلی را پاک می‌کنیم تا دفعات بعد مانع باز شدن پنل نشود.
        _CIRCLE_PANEL_MESSAGES.pop(owner_id, None)


# ---------------------------------------------------------------------------
# callback دعوت: cinvite:<accept|cancel>:<target_id>:<circle_id>:<inviter_id>
# ---------------------------------------------------------------------------


@router.callback_query(lambda c: c.data and c.data.startswith("cinvite:"))
async def on_circle_invitation_callback(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer()
        return

    action = parts[1]
    try:
        target_id = int(parts[2])
        circle_id = int(parts[3])
        inviter_id = int(parts[4])
    except ValueError:
        await callback.answer()
        return

    if callback.from_user.id != target_id:
        await callback.answer("این دعوت برای تو نیست.", show_alert=True)
        return

    if action == "cancel":
        await callback.answer()
        await callback.message.edit_text(texts.CIRCLE_INVITE_DECLINED)
        return

    if action != "accept":
        await callback.answer()
        return

    async with async_session_factory() as session:
        async with session.begin():
            target_user = await get_or_create_user(
                session,
                target_id,
                callback.from_user.username,
                callback.from_user.first_name,
            )
            inviter = await get_user_by_telegram_id(session, inviter_id)
            circle = await session.get(DhikrCircle, circle_id)

            if target_user.level < 2:
                await callback.answer(texts.CIRCLE_INVITE_TARGET_NOT_LEVEL_2, show_alert=True)
                return
            if circle is None or inviter is None or inviter.active_circle_id != circle_id:
                await callback.answer(texts.CIRCLE_INVITE_EXPIRED, show_alert=True)
                return
            if target_user.active_circle_id == circle_id:
                await callback.answer("شما همین حالا عضو این حلقه هستید.", show_alert=True)
                return
            if target_user.active_circle_id is not None:
                await callback.answer(texts.CIRCLE_JOIN_ALREADY_IN_CIRCLE, show_alert=True)
                return

            # توجه: حلقه سقف ظرفیت ندارد (فقط ۵ نفر شرط پاداش گروهی است)، پس اینجا
            # دیگر active_count/FULL بررسی نمی‌شود.
            outcome = await join_circle(session, target_user, circle_id)

    if outcome.result == JoinCircleResult.ALREADY_IN_CIRCLE:
        await callback.answer(texts.CIRCLE_JOIN_ALREADY_IN_CIRCLE, show_alert=True)
        return
    if outcome.result == JoinCircleResult.FULL:
        await callback.answer(texts.CIRCLE_INVITE_FULL, show_alert=True)
        return
    if outcome.result == JoinCircleResult.COOLDOWN:
        await callback.answer(
            texts.circle_join_locked(_hours_left(outcome.cooldown_until)), show_alert=True
        )
        return
    if outcome.result != JoinCircleResult.SUCCESS:
        await callback.answer(texts.CIRCLE_INVITE_EXPIRED, show_alert=True)
        return

    await callback.answer()
    # پنل حلقه در PV فرستاده نمی‌شود؛ فقط پیام تأیید.
    # برای دیدن پنل، کاربر در گروه بنویسد: «حلقه ذکر»
    await callback.message.edit_text(
        "✅ دعوت را قبول کردی و وارد حلقه شدی.\n\n"
        "برای دیدن پنل حلقه، در گروه بنویس: «حلقه ذکر»"
    )


# ---------------------------------------------------------------------------
# callbackهای پنل: crc:<action>:<owner_id>
# ---------------------------------------------------------------------------


async def _guard_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user is None or callback.from_user.id != owner_id:
        await callback.answer("این پنل مال تو نیست.", show_alert=True)
        return False
    return True


@router.callback_query(lambda c: c.data and c.data.startswith("crc:"))
async def on_circle_callback(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return

    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    try:
        owner_id = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        owner_id = None

    if owner_id is None or not await _guard_owner(callback, owner_id):
        return

    handler = _ACTIONS.get(action)
    if handler is None:
        await callback.answer()
        return
    await handler(callback, owner_id, parts)


async def _show_main(callback: CallbackQuery, owner_id: int, parts: list[str]) -> None:
    if await _send_circle_panel(callback, owner_id, edit=True):
        await callback.answer()
        return
    await callback.answer(texts.CIRCLE_NOT_IN_CIRCLE, show_alert=True)


async def _create(callback: CallbackQuery, owner_id: int, parts: list[str]) -> None:
    async with async_session_factory() as session:
        user = await get_or_create_user(
            session, owner_id, callback.from_user.username, callback.from_user.first_name
        )
        if user.level < 2:
            await callback.answer(texts.CIRCLE_INVITE_REQUIRES_LEVEL_2, show_alert=True)
            return
        if user.active_circle_id is not None:
            await callback.answer(texts.circle_already_in_circle(), show_alert=True)
            return

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )
            if user.level < 2:
                await callback.answer(texts.CIRCLE_INVITE_REQUIRES_LEVEL_2, show_alert=True)
                return
            if user.active_circle_id is not None:
                await callback.answer()
                await _send_circle_panel(callback, owner_id, edit=True)
                return

            outcome = await create_circle(session, user)

    if outcome.result == CreateCircleResult.SUCCESS:
        await callback.answer()
        await _send_circle_panel(callback, owner_id, edit=True)
    elif outcome.result == CreateCircleResult.ALREADY_IN_CIRCLE:
        await callback.answer()
        await _send_circle_panel(callback, owner_id, edit=True)
    else:
        await callback.answer("ساخت حلقه انجام نشد؛ دوباره امتحان کن.", show_alert=True)


async def _invite(callback: CallbackQuery, owner_id: int, parts: list[str]) -> None:
    async with async_session_factory() as session:
        user = await get_or_create_user(
            session, owner_id, callback.from_user.username, callback.from_user.first_name
        )
        if user.active_circle_id is None:
            await callback.answer(texts.CIRCLE_NOT_IN_CIRCLE, show_alert=True)
            return

    # نوتیف کوتاه — Alert تلگرام محدود به ~۲۰۰ کاراکتره، پس خلاصه‌ست.
    await callback.answer(
        "🔗 راهنمای دعوت:\n"
        "روی پیام شخص موردنظر ریپلای کن و بنویس «حلقه ذکر».\n\n"
        "بعد برای او یک پیام خصوصی با دکمه‌های «✅ قبول دعوت» و «❌ رد دعوت» می‌آید.",
        show_alert=True,
    )


async def _leave_ask(callback: CallbackQuery, owner_id: int, parts: list[str]) -> None:
    async with async_session_factory() as session:
        user = await get_or_create_user(
            session, owner_id, callback.from_user.username, callback.from_user.first_name
        )
        if user.active_circle_id is None:
            await callback.answer(texts.CIRCLE_NOT_IN_CIRCLE, show_alert=True)
            return

    await callback.answer()
    await callback.message.edit_text(
        texts.circle_leave_ask(), reply_markup=circle_leave_confirm_keyboard(owner_id)
    )


async def _leave_confirm(callback: CallbackQuery, owner_id: int, parts: list[str]) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(
                session,
                owner_id,
                callback.from_user.username,
                callback.from_user.first_name,
            )
            outcome = await leave_circle(session, user)

    if outcome.result == LeaveCircleResult.NOT_IN_CIRCLE:
        await callback.answer(texts.CIRCLE_NOT_IN_CIRCLE, show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(texts.CIRCLE_LEFT_SUCCESS)


async def _leave_cancel(callback: CallbackQuery, owner_id: int, parts: list[str]) -> None:
    await _show_main(callback, owner_id, parts)


async def _claim_reward(callback: CallbackQuery, owner_id: int, parts: list[str]) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )
            outcome = await claim_circle_personal_reward(session, user)

    if outcome.result == ClaimPersonalRewardResult.NOT_IN_CIRCLE:
        await callback.answer(texts.CIRCLE_NOT_IN_CIRCLE, show_alert=True)
        return
    if outcome.result == ClaimPersonalRewardResult.NOT_READY:
        await callback.answer(texts.CIRCLE_REWARD_NOT_READY, show_alert=True)
        return
    if outcome.result == ClaimPersonalRewardResult.ALREADY_CLAIMED:
        await callback.answer(texts.CIRCLE_REWARD_ALREADY_CLAIMED, show_alert=True)
        return

    await callback.answer()

    mention = build_user_mention(user)
    try:
        await callback.message.answer(
            texts.circle_reward_group_announcement(mention, outcome.reward_noor),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("ارسال پیام گروهی دریافت جایزه‌ی حلقه ناموفق بود (user_id=%s)", owner_id)

    await _send_circle_panel(callback, owner_id, edit=True)


_ACTIONS = {
    "main": _show_main,
    "create": _create,
    "invite": _invite,
    "leave_ask": _leave_ask,
    "leave_confirm": _leave_confirm,
    "leave_cancel": _leave_cancel,
    "claim_reward": _claim_reward,
}


# ---------------------------------------------------------------------------
# دعوت با Reply — تنها روش دعوت
# ---------------------------------------------------------------------------


async def invite_user_from_message(message: Message, bot) -> bool:
    """
    فقط حالت Reply پشتیبانی می‌شود:
      روی پیام شخص موردنظر ریپلای کن و بنویس «حلقه ذکر».

    خروجی:
      True  -> این پیام مصرف شد (دعوت انجام شد یا خطا داده شد)
      False -> این پیام به این تابع مربوط نبود؛ بگذار بقیه‌ی handlerها بررسی کنند.
    """
    if message.from_user is None or message.text is None:
        return False

    normalized = normalize_text(" ".join(message.text.strip().split()))

    # اگر بعد از «حلقه ذکر» آرگومان آمده (@username یا ID)، چون دیگر پشتیبانی نمی‌شود،
    # پیام راهنما می‌دهیم و تمام.
    if normalized.startswith(COMMAND_DHIKR_CIRCLE + " "):
        await message.reply(
            "برای دعوت فقط از روش ریپلای استفاده کن:\n"
            "روی پیام شخص موردنظر ریپلای کن و بنویس: «حلقه ذکر»"
        )
        return True

    # فقط «حلقه ذکر» بدون آرگومان
    if normalized != COMMAND_DHIKR_CIRCLE:
        return False

    # اگر Reply نیست، این پیام مربوط به دستور حلقه ذکر (ساخت/نمایش پنل) است، نه دعوت.
    if message.reply_to_message is None:
        return False

    target = message.reply_to_message.from_user
    inviter_id = message.from_user.id

    if target is None:
        return False
    if target.is_bot:
        await message.reply("❌ نمی‌شود یک ربات را به حلقه دعوت کرد.")
        return True
    if target.id == inviter_id:
        await message.reply("❌ نمی‌توانی خودت را دعوت کنی.")
        return True

    target_id = target.id

    async with async_session_factory() as session:
        inviter = await get_or_create_user(
            session,
            inviter_id,
            message.from_user.username,
            message.from_user.first_name,
        )
        if inviter.level < 2:
            await message.reply(texts.CIRCLE_INVITE_REQUIRES_LEVEL_2)
            return True
        if inviter.active_circle_id is None:
            await message.reply(texts.CIRCLE_NOT_IN_CIRCLE)
            return True

        circle = await session.get(DhikrCircle, inviter.active_circle_id)
        if circle is None:
            await message.reply(texts.CIRCLE_NOT_IN_CIRCLE)
            return True

        # همه‌ی اعضای یک حلقه‌ی فعال می‌توانند عضو جدید دعوت کنند.
        # creator بودن شرط دعوت نیست؛ شرط این است که دعوت‌کننده خودش عضو همین حلقه باشد.

        target_user = await get_user_by_telegram_id(session, target_id)
        if target_user is not None and target_user.active_circle_id is not None:
            # active_circle_id ممکن است از یک حلقه‌ی حذف‌شده باقی مانده باشد.
            # فقط وجود یک عضویت فعال واقعی باید مانع دعوت شود.
            target_circle = await session.get(DhikrCircle, target_user.active_circle_id)
            if target_circle is None:
                target_user.active_circle_id = None
                await session.flush()
            elif target_user.active_circle_id == circle.id:
                await message.reply("این شخص همین حالا عضو این حلقه است.")
                return True
            else:
                target_membership = await get_active_membership(session, target_user)
                if target_membership is None:
                    target_user.active_circle_id = None
                    await session.flush()
                else:
                    await message.reply(texts.CIRCLE_INVITE_TARGET_ALREADY_IN_CIRCLE)
                    return True
        if target_user is not None and target_user.level < 2:
            await message.reply(texts.CIRCLE_INVITE_TARGET_NOT_LEVEL_2)
            return True

        # توجه: حلقه سقف ظرفیت ندارد (فقط ۵ نفر شرط پاداش گروهی است)، پس اینجا
        # دیگر active_count/FULL بررسی نمی‌شود.
        inviter_label = _member_label(inviter)
        target_label = (
            _member_label(target_user) if target_user is not None else _member_label(target)
        )
        circle_id = circle.id

    try:
        await bot.send_message(
            target_id,
            texts.circle_invite_confirmation(target_label, inviter_label),
            reply_markup=circle_invite_confirmation_keyboard(target_id, circle_id, inviter_id),
        )
    except Exception:
        logger.exception("ارسال دعوت حلقه به کاربر %s ناموفق بود", target_id)
        await message.reply(texts.CIRCLE_INVITE_TARGET_MUST_START_BOT)
        return True

    await message.reply(texts.circle_invite_sent(target_label))
    return True


async def expire_circle_panels(bot) -> None:
    """
    پنل‌های حلقه‌های منقضی‌شده را حذف می‌کند.

    این تابع توسط scheduler فراخوانی می‌شود؛ بعد از حذف پنل Telegram،
    cache مربوط به همان پیام‌ها هم پاک می‌شود.
    """
    try:
        async with async_session_factory() as session:
            async with session.begin():
                targets = await expire_expired_circles(session)

        for chat_id, message_id in targets:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                logger.debug(
                    "حذف پنل حلقه منقضی‌شده ناموفق بود (chat=%s, message=%s)",
                    chat_id,
                    message_id,
                    exc_info=True,
                )

        if targets:
            expired_message_ids = {(chat_id, message_id) for chat_id, message_id in targets}
            for telegram_id, target in list(_CIRCLE_PANEL_MESSAGES.items()):
                if target in expired_message_ids:
                    _CIRCLE_PANEL_MESSAGES.pop(telegram_id, None)
    except Exception:
        logger.exception("خطا در حذف پنل‌های حلقه‌های منقضی‌شده")



# سازگاری با کدهای قبلی
invite_user_from_reply = invite_user_from_message
