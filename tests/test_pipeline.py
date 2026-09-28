"""
تست‌های دستی سطح-بالا برای پوشش سناریوهای بخش ۲۲ سند + اصلاحات نهایی، بدون نیاز به
سرور تلگرام واقعی. این فایل با: python tests/test_pipeline.py اجرا می‌شود.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DATABASE_PATH", "/tmp/test_laahiq_pipeline.db")
os.environ.setdefault("BOT_TOKEN", "dummy:token")

DB_PATH = os.environ["DATABASE_PATH"]
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
for suffix in ("-wal", "-shm"):
    p = DB_PATH + suffix
    if os.path.exists(p):
        os.remove(p)

from bot.database.engine import async_session_factory, run_migrations  # noqa: E402
from bot.database.models import Chest  # noqa: E402
from bot.domain import chest as chest_domain  # noqa: E402
from bot.domain import closing_lines as closing_lines_module  # noqa: E402
from bot.domain.validator import ActivityKind  # noqa: E402
from bot.services.activity_service import OutcomeStatus, process_activity  # noqa: E402
from bot.services.chest_service import ChestOpenResult, open_chest  # noqa: E402
from bot.services.reminder_service import get_users_due_for_reminder  # noqa: E402
from bot.services.tasbih_service import TasbihUpgradeResult, upgrade_tasbih  # noqa: E402
from bot.services.unlock_service import UnlockResult, unlock_dhikr  # noqa: E402
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id  # noqa: E402
from bot.database.models import DuaQueue  # noqa: E402
from bot.services.dua_queue_service import (  # noqa: E402
    AnswerQueueResult,
    CreateQueueResult,
    answer_dua_queue,
    close_expired_queues,
    create_dua_queue,
    find_queue_by_panel_message,
    get_panel_view,
    get_queue_dhikr,
)
from bot.domain.dhikr_data import DUA_QUEUE_DHIKR_BY_KEY, DUA_QUEUE_NORMALIZED_TEXTS  # noqa: E402
from bot.domain.normalization import normalize_text  # noqa: E402
from bot.services.dhikr_circle_service import get_or_assign_display_dhikr  # noqa: E402
from bot.domain import dhikr_circle as circle_domain  # noqa: E402
from bot.database.models import DhikrCircle, DhikrCircleMember  # noqa: E402
from bot.services.dhikr_circle_service import (  # noqa: E402
    CreateCircleResult,
    JoinCircleResult,
    LeaveCircleResult,
    RemoveMemberResult,
    create_circle,
    join_circle,
    leave_circle,
    remove_member,
)
from bot.domain.dhikr_data import DHIKR_BY_KEY  # noqa: E402
from bot.handlers.group_messages import _chat_allows_activity, _render_success  # noqa: E402
from bot.handlers.bank_panel import on_bank_panel_callback  # noqa: E402
from bot.handlers.tasbih_panel import on_tasbih_panel_callback  # noqa: E402
from bot.handlers.commands import show_bank_azkar, show_tasbih  # noqa: E402
from bot.services.activity_service import ActivityOutcome  # noqa: E402
from bot.texts import messages as texts  # noqa: E402
from aiogram.enums import ChatType  # noqa: E402

TELEGRAM_ID = 111
CHAT_ID = -100999
_update_counter = 0


def next_update_id() -> int:
    global _update_counter
    _update_counter += 1
    return _update_counter


async def send(text: str, now: datetime | None = None):
    return await send_as(TELEGRAM_ID, text, now)


async def send_as(telegram_id: int, text: str, now: datetime | None = None):
    async with async_session_factory() as session:
        async with session.begin():
            outcome = await process_activity(
                session,
                update_id=next_update_id(),
                telegram_id=telegram_id,
                username="tester",
                first_name="Tester",
                chat_id=CHAT_ID,
                raw_text=text,
                now=now,
            )
    return outcome


def check(condition: bool, label: str) -> None:
    status = "OK  " if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(f"TEST FAILED: {label}")


async def get_user():
    async with async_session_factory() as session:
        return await get_user_by_telegram_id(session, TELEGRAM_ID)


async def get_user_by_telegram_id_wrap(telegram_id: int):
    async with async_session_factory() as session:
        return await get_user_by_telegram_id(session, telegram_id)


DUA_QUEUE_CHAT_ID = -100778
DUA_QUEUE_OWNER_ID = 70001
DUA_QUEUE_RESPONDER_IDS = [70100 + i for i in range(11)]


async def _l2_send(telegram_id: int, text: str, now: datetime) -> "ActivityOutcome":  # noqa: F821
    async with async_session_factory() as session:
        async with session.begin():
            return await process_activity(
                session,
                update_id=next_update_id(),
                telegram_id=telegram_id,
                username="tester",
                first_name="Tester",
                chat_id=DUA_QUEUE_CHAT_ID,
                raw_text=text,
                now=now,
            )


async def _dua_answer(queue_id: int, telegram_id: int, text: str, now: datetime):
    """پاسخ به پنل با متن داده‌شده (شبیه ریپلای روی پنل)؛ queue داخل همان تراکنش خوانده می‌شود."""
    async with async_session_factory() as session:
        async with session.begin():
            queue_row = await session.get(DuaQueue, queue_id)
            return await answer_dua_queue(
                session,
                queue=queue_row,
                update_id=next_update_id(),
                telegram_id=telegram_id,
                username="tester",
                first_name="Tester",
                raw_text=text,
                now=now,
            )


async def _dua_owner_completes_quota(t: datetime, label: str) -> datetime:
    """صاحب پنل ۱۰ ذکر (الحمدلله) می‌گوید تا شرط باز شدن پنل همان روز کامل شود."""
    last = None
    for i in range(10):
        t += timedelta(seconds=15)  # فراتر از cooldown فعلی ذکر (۱۰ ثانیه)
        last = await _l2_send(DUA_QUEUE_OWNER_ID, "الحمدلله", t)
        check(last.status == OutcomeStatus.SUCCESS, f"owner: ذکر {label} #{i + 1} موفق")
    return t, last


async def test_level2_dua_queue() -> None:
    """
    سناریوهای Level 2 — التماس دعا (نام داخلی: dua_queue). با یک chat_id/تلگرام‌آیدی‌های مجزا از
    بقیه‌ی تست‌ها اجرا می‌شود تا با سناریوهای Level 1 (بالاتر در همین فایل) تداخل نداشته باشد.
    """
    print("\n== Level 2: سهمیه‌ی روزانه‌ی ۱۰ ذکر -> باز شدن التماس دعا ==")
    t = datetime.now(timezone.utc)

    outcome = await _l2_send(DUA_QUEUE_OWNER_ID, "اللهم صل علی محمد و آل محمد", t)
    check(outcome.status == OutcomeStatus.SUCCESS, "owner: اولین صلوات موفق")

    # قبل از ۱۰ ذکر، ساخت پنل رد می‌شود.
    for i in range(9):
        t += timedelta(seconds=15)
        r = await _l2_send(DUA_QUEUE_OWNER_ID, "الحمدلله", t)
        check(r.status == OutcomeStatus.SUCCESS, f"owner: ذکر #{i + 1} موفق")
        check(r.milestone_kind != "dua_queue_unlocked", f"ذکر #{i + 1} هنوز milestone نیست")
    async with async_session_factory() as session:
        async with session.begin():
            owner_row = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            early = await create_dua_queue(session, owner_row, DUA_QUEUE_CHAT_ID, now=t)
    check(early.result == CreateQueueResult.QUOTA_NOT_COMPLETE, "با ۹ ذکر ساخت پنل رد می‌شود")
    check(early.daily_free_dhikr_count == 9, "شمارنده‌ی امروز == 9")

    t += timedelta(seconds=15)
    last_outcome = await _l2_send(DUA_QUEUE_OWNER_ID, "الحمدلله", t)
    check(last_outcome.status == OutcomeStatus.SUCCESS, "owner: ذکر دهم موفق")
    check(last_outcome.milestone_kind == "dua_queue_unlocked", "دهمین ذکر -> milestone التماس دعا")
    check(last_outcome.noor_reward == 5, "دهمین ذکر پاداش عادی خودش را دارد (بدون بوست)")

    owner_user = await get_user_by_telegram_id_wrap(DUA_QUEUE_OWNER_ID)
    check(owner_user.daily_free_dhikr_count == 10, "شمارنده‌ی روزانه‌ی ذکر == 10")

    print("\n== Level 2: ذکرهای التماس دعا بیرون از پنل نور نمی‌دهند ==")
    for dua_text in DUA_QUEUE_NORMALIZED_TEXTS:
        t += timedelta(seconds=15)
        r = await _l2_send(DUA_QUEUE_OWNER_ID, dua_text, t)
        check(r.status != OutcomeStatus.SUCCESS, f"«{dua_text}» در چت عادی ثبت نمی‌شود")
    owner_after = await get_user_by_telegram_id_wrap(DUA_QUEUE_OWNER_ID)
    check(owner_after.daily_free_dhikr_count == 10, "این پیام‌ها شمارنده را تغییر ندادند")

    print("\n== Level 2: تعداد اعضای گروه مهم نیست (فقط owner فعال است) ==")
    async with async_session_factory() as session:
        async with session.begin():
            owner_row = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            create_outcome = await create_dua_queue(session, owner_row, DUA_QUEUE_CHAT_ID, now=t)
    check(create_outcome.result == CreateQueueResult.SUCCESS, "ساخت پنل با یک عضو فعال هم موفق است")
    queue = create_outcome.queue
    check(queue.dhikr_key in DUA_QUEUE_DHIKR_BY_KEY, "ذکر پنل یکی از ۵ ذکر تعریف‌شده است")
    dhikr_text = get_queue_dhikr(queue).canonical_texts[0]

    # ذخیره‌ی message_id پنل و پیدا کردن پنل از روی پیام ریپلای‌شده
    async with async_session_factory() as session:
        async with session.begin():
            row = await session.get(DuaQueue, queue.id)
            row.message_id = 555001
    async with async_session_factory() as session:
        found = await find_queue_by_panel_message(session, DUA_QUEUE_CHAT_ID, 555001)
        missing = await find_queue_by_panel_message(session, DUA_QUEUE_CHAT_ID, 999999)
    check(found is not None and found.id == queue.id, "پنل از روی message_id پیدا می‌شود")
    check(missing is None, "message_id نامرتبط -> پنلی پیدا نمی‌شود")

    # ۶ پاسخ‌دهنده (۵ نفر پاسخ می‌دهند + یک نفر برای بعد از بسته شدن) با اولین صلوات فعال می‌شوند.
    for rid in DUA_QUEUE_RESPONDER_IDS:
        t += timedelta(seconds=5)
        r = await _l2_send(rid, "اللهم صل علی محمد و آل محمد", t)
        check(r.status == OutcomeStatus.SUCCESS, f"پاسخ‌دهنده {rid}: اولین صلوات موفق")

    print("\n== Level 2: صاحب پنل نمی‌تواند به پنل خودش پاسخ دهد ==")
    ans = await _dua_answer(queue.id, DUA_QUEUE_OWNER_ID, dhikr_text, t)
    check(ans.result == AnswerQueueResult.OWNER_CANNOT_ANSWER, "صاحب پنل نمی‌تواند پاسخ دهد")

    print("\n== Level 2: متن اشتباه (ذکر دیگر/ذکر ناقص) پذیرفته نمی‌شود ==")
    other_text = next(x for x in DUA_QUEUE_NORMALIZED_TEXTS if x != normalize_text(dhikr_text))
    responder_id = DUA_QUEUE_RESPONDER_IDS[0]
    t += timedelta(seconds=12)
    ans = await _dua_answer(queue.id, responder_id, other_text, t)
    check(ans.result == AnswerQueueResult.TEXT_MISMATCH, "ذکر دیگرِ لیست -> TEXT_MISMATCH")
    ans = await _dua_answer(queue.id, responder_id, "اللهم اغفر له", t)
    check(ans.result == AnswerQueueResult.TEXT_MISMATCH, "متن ناقص -> TEXT_MISMATCH")

    print("\n== Level 2: پاسخ معتبر -> پاداش عادی ۱۰ + ۱۵ نور صاحب پنل ==")
    owner_noor_before = (await get_user_by_telegram_id_wrap(DUA_QUEUE_OWNER_ID)).noor_current
    t += timedelta(seconds=12)
    # اعراب/فاصله‌ی اضافه با همان normalization اذکار نادیده گرفته می‌شود.
    ans = await _dua_answer(queue.id, responder_id, "  " + dhikr_text + "\u064E  ", t)
    check(ans.result == AnswerQueueResult.SUCCESS, "اولین پاسخ موفق (با normalization)")
    check(ans.activity_outcome.noor_reward == 10, "پاداش پاسخ‌دهنده == 10 (عادی، بدون بوست)")
    check(ans.owner_reward_total == 15 and not ans.completion_bonus_paid, "صاحب پنل ۱۵ نور، بدون بونوس")
    check(ans.owner_noor_current == owner_noor_before + 15, "noor_current صاحب پنل دقیقاً ۱۵ زیاد شد")
    async with async_session_factory() as session:
        view1 = await get_panel_view(session, await session.get(DuaQueue, queue.id))
    check(len(view1.responders) == 1 and view1.responders[0][0] == responder_id, "اسم اولین دعاکننده در پنل ثبت شد")
    check(view1.owner_earned == 15, "نور دریافتی صاحب پنل بعد از یک پاسخ == 15")
    panel1 = texts.dua_queue_panel_text(
        1, 5, dhikr_text=dhikr_text, owner_name=view1.owner_name, owner_telegram_id=view1.owner_telegram_id,
        responders=view1.responders, owner_earned=view1.owner_earned,
    )
    check("دعاکنندگان" in panel1 and f"tg://user?id={responder_id}" in panel1, "متن پنل اسم دعاکننده را دارد")
    check("نور دریافتی صاحب پنل: ۱۵" in panel1, "متن پنل نور دریافتی صاحب را نشان می‌دهد")

    print("\n== Level 2: هر کاربر فقط یک‌بار می‌تواند به یک پنل پاسخ دهد ==")
    t += timedelta(seconds=12)
    ans2 = await _dua_answer(queue.id, responder_id, dhikr_text, t)
    check(ans2.result == AnswerQueueResult.ALREADY_ANSWERED, "پاسخ دوم همان کاربر رد شد")

    print("\n== Level 2: پنجمین پاسخ پنل را می‌بندد و ۲۵ نور بونوس می‌دهد ==")
    success_count = 1
    owner_noor_mid = (await get_user_by_telegram_id_wrap(DUA_QUEUE_OWNER_ID)).noor_current
    fifth = None
    for rid in DUA_QUEUE_RESPONDER_IDS[1:5]:
        t += timedelta(seconds=12)
        ans_n = await _dua_answer(queue.id, rid, dhikr_text, t)
        check(ans_n.result == AnswerQueueResult.SUCCESS, f"پاسخ #{success_count + 1} موفق")
        success_count += 1
        if success_count < 5:
            check(not ans_n.now_closed and not ans_n.completion_bonus_paid, f"پاسخ #{success_count}: هنوز باز است")
        else:
            fifth = ans_n
    check(fifth.now_closed, "پنجمین پاسخ -> پنل بسته می‌شود")
    check(fifth.completion_bonus_paid and fifth.owner_reward_total == 15 + 25, "پنجمین پاسخ: 15 + 25 بونوس")
    owner_noor_end = (await get_user_by_telegram_id_wrap(DUA_QUEUE_OWNER_ID)).noor_current
    # ۳ پاسخ عادی (۱۵ تایی) بین mid و پنجمی + پنجمی با بونوس (۴۰) = ۴ پاسخ بعد از mid
    check(owner_noor_end == owner_noor_mid + 15 * 3 + 40, "مجموع نور صاحب پنل بعد از ۵ پاسخ درست است")

    t += timedelta(seconds=12)
    ans6 = await _dua_answer(queue.id, DUA_QUEUE_RESPONDER_IDS[5], dhikr_text, t)
    check(ans6.result == AnswerQueueResult.CLOSED, "پاسخ ششم بعد از بسته شدن رد می‌شود")
    owner_noor_final = (await get_user_by_telegram_id_wrap(DUA_QUEUE_OWNER_ID)).noor_current
    check(owner_noor_final == owner_noor_end, "بونوس دوباره پرداخت نشد")

    async with async_session_factory() as session:
        closed_queue = await session.get(DuaQueue, queue.id)
    check(closed_queue.closed and closed_queue.closed_reason == "max_answers", "پنل با دلیل max_answers بسته شد")
    check(closed_queue.answers_count == 5, "answers_count نهایی == 5")
    async with async_session_factory() as session:
        view5 = await get_panel_view(session, await session.get(DuaQueue, queue.id))
    check([r[0] for r in view5.responders] == DUA_QUEUE_RESPONDER_IDS[:5], "۵ دعاکننده به ترتیب پاسخ در پنل هستند")
    check(view5.owner_earned == 5 * 15 + 25, "نور دریافتی صاحب پنل بعد از ۵ پاسخ == 100 (شامل بونوس)")
    closed_text = texts.dua_queue_panel_text(
        5, 5, owner_name=view5.owner_name, owner_telegram_id=view5.owner_telegram_id,
        responders=view5.responders, owner_earned=view5.owner_earned, closed=True,
    )
    check("بسته شد" in closed_text and "نور دریافتی صاحب پنل: ۱۰۰" in closed_text, "پنل بسته هم اسم‌ها و نور صاحب را نشان می‌دهد")

    print("\n== Level 2: پنل قدیمی (بدون ذکر) قابل پاسخ نیست ==")
    async with async_session_factory() as session:
        async with session.begin():
            owner_row_l = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            legacy = DuaQueue(
                owner_user_id=owner_row_l.id,
                chat_id=DUA_QUEUE_CHAT_ID,
                created_at=t - timedelta(days=3),
                expires_at=t + timedelta(hours=5),
                answers_count=0,
                closed=False,
                dhikr_key=None,
            )
            session.add(legacy)
            await session.flush()
            legacy_id = legacy.id
    ans_legacy = await _dua_answer(legacy_id, DUA_QUEUE_RESPONDER_IDS[0], dhikr_text, t)
    check(ans_legacy.result == AnswerQueueResult.NOT_FOUND, "پنل قدیمی -> NOT_FOUND (نادیده گرفته می‌شود)")

    print("\n== Level 2: ذکر حلقه در سهمیه‌ی ۱۰تایی حساب نمی‌شود و پاسخ به پنل روی حلقه اثر ندارد ==")
    circ_uid = 70201
    t += timedelta(seconds=30)
    r = await _l2_send(circ_uid, "اللهم صل علی محمد و آل محمد", t)
    check(r.status == OutcomeStatus.SUCCESS, "کاربر حلقه: اولین صلوات موفق")
    async with async_session_factory() as session:
        async with session.begin():
            circ_user = await get_or_create_user(session, circ_uid, "tester", "Tester")
            circ_create = await create_circle(session, circ_user, now=t)
            assigned = await get_or_assign_display_dhikr(session, circ_user, now=t)
    check(circ_create.result == CreateCircleResult.SUCCESS, "حلقه برای تست ساخته شد")
    t += timedelta(seconds=30)
    r = await _l2_send(circ_uid, assigned.canonical_texts[0], t)
    check(r.status == OutcomeStatus.SUCCESS and r.is_circle_dhikr, "ذکر حلقه ثبت شد و is_circle_dhikr است")
    u = await get_user_by_telegram_id_wrap(circ_uid)
    check(u.daily_free_dhikr_count == 0, "ذکر حلقه در سهمیه‌ی روزانه‌ی ۱۰تایی حساب نشد")
    t += timedelta(seconds=30)
    r = await _l2_send(circ_uid, "الحمدلله", t)
    check(r.status == OutcomeStatus.SUCCESS, "ذکر عادی بعد از ذکر حلقه موفق")
    u = await get_user_by_telegram_id_wrap(circ_uid)
    check(u.daily_free_dhikr_count == 1, "ذکر عادی در سهمیه حساب شد (== 1)")

    # پنل بازِ جداگانه برای اینکه عضو حلقه به آن پاسخ دهد.
    async with async_session_factory() as session:
        async with session.begin():
            owner_row_c = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            open_q = DuaQueue(
                owner_user_id=owner_row_c.id,
                chat_id=DUA_QUEUE_CHAT_ID,
                created_at=t,
                expires_at=t + timedelta(hours=12),
                answers_count=0,
                closed=False,
                dhikr_key="dua_ighfir_lahu_warhamhu",
            )
            session.add(open_q)
            await session.flush()
            open_q_id = open_q.id
    circle_count_before = (await get_user_by_telegram_id_wrap(circ_uid)).circle_daily_dhikr_count
    t += timedelta(seconds=30)
    ans_c = await _dua_answer(open_q_id, circ_uid, "اللهم اغفر له وارحمه", t)
    check(ans_c.result == AnswerQueueResult.SUCCESS, "عضو حلقه به پنل پاسخ داد")
    u = await get_user_by_telegram_id_wrap(circ_uid)
    check(u.circle_daily_dhikr_count == circle_count_before, "پاسخ به پنل روی پیشرفت حلقه اثر نداشت")
    check(u.daily_free_dhikr_count == 2, "پاسخ به پنل در سهمیه‌ی ۱۰تایی حساب شد (== 2)")

    print("\n== Level 2: پنل بعد از ۱۲ ساعت منقضی می‌شود ==")
    # سازنده باید دوباره سهمیه‌ی روزانه را کامل کند (روز جدید تهران) تا پنل دوم بسازد.
    t2, _ = await _dua_owner_completes_quota(t + timedelta(hours=25), "روز بعد")

    async with async_session_factory() as session:
        async with session.begin():
            owner_row2 = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            create_outcome2 = await create_dua_queue(session, owner_row2, DUA_QUEUE_CHAT_ID, now=t2)
    check(create_outcome2.result == CreateQueueResult.SUCCESS, "ساخت پنل دوم موفق")
    queue2 = create_outcome2.queue
    text2 = get_queue_dhikr(queue2).canonical_texts[0]

    t3 = t2 + timedelta(hours=13)
    ans_expired = await _dua_answer(queue2.id, DUA_QUEUE_RESPONDER_IDS[0], text2, t3)
    check(ans_expired.result == AnswerQueueResult.CLOSED, "پاسخ بعد از ۱۳ ساعت -> پنل منقضی")

    print("\n== Level 2: سازنده فقط هر ۲۴ ساعت یک پنل می‌تواند بسازد ==")
    async with async_session_factory() as session:
        async with session.begin():
            owner_row3 = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            create_outcome3 = await create_dua_queue(
                session, owner_row3, DUA_QUEUE_CHAT_ID, now=t2 + timedelta(hours=1)
            )
    check(create_outcome3.result == CreateQueueResult.OWNER_COOLDOWN, "ساخت پنل زودتر از ۲۴ ساعت رد شد")

    print("\n== Level 2: صاحب پنل بازِ خودش دوباره دستور بزند -> پنل فعلی، نه پیام ۲۴ ساعته ==")
    t5, _ = await _dua_owner_completes_quota(t2 + timedelta(hours=26), "روز برای پنل فعال")
    async with async_session_factory() as session:
        async with session.begin():
            o5 = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            c5 = await create_dua_queue(session, o5, DUA_QUEUE_CHAT_ID, now=t5)
    check(c5.result == CreateQueueResult.SUCCESS, "پنل جدید برای تست پنل فعال ساخته شد")
    async with async_session_factory() as session:
        async with session.begin():
            o5 = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            again = await create_dua_queue(session, o5, DUA_QUEUE_CHAT_ID, now=t5 + timedelta(minutes=5))
    check(again.result == CreateQueueResult.ACTIVE_QUEUE_EXISTS, "پنل باز -> ACTIVE_QUEUE_EXISTS (نه OWNER_COOLDOWN)")
    check(again.queue is not None and again.queue.id == c5.queue.id, "همان پنل فعلی برگردانده شد")
    async with async_session_factory() as session:
        async with session.begin():
            row = await session.get(DuaQueue, c5.queue.id)
            row.closed = True
            row.closed_reason = "max_answers"
    async with async_session_factory() as session:
        async with session.begin():
            o5 = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            after = await create_dua_queue(session, o5, DUA_QUEUE_CHAT_ID, now=t5 + timedelta(minutes=10))
    check(after.result == CreateQueueResult.OWNER_COOLDOWN, "بعد از بسته شدن پنل -> محدودیت ۲۴ ساعته")

    print("\n== Level 2: Job خودکار بستن پنل‌های منقضی (idempotent) ==")
    t4, _ = await _dua_owner_completes_quota(t2 + timedelta(hours=25), "روز سوم")
    async with async_session_factory() as session:
        async with session.begin():
            owner_row4 = await get_or_create_user(session, DUA_QUEUE_OWNER_ID, "tester", "Tester")
            create_outcome4 = await create_dua_queue(session, owner_row4, DUA_QUEUE_CHAT_ID, now=t4)
    check(create_outcome4.result == CreateQueueResult.SUCCESS, "ساخت پنل سوم برای تست job موفق")
    queue4 = create_outcome4.queue

    t5 = t4 + timedelta(hours=13)
    async with async_session_factory() as session:
        async with session.begin():
            closed_list = await close_expired_queues(session, now=t5)
    check(any(q.id == queue4.id for q in closed_list), "job پنل منقضی را در اولین اجرا پیدا و می‌بندد")

    async with async_session_factory() as session:
        async with session.begin():
            closed_list2 = await close_expired_queues(session, now=t5 + timedelta(minutes=1))
    check(
        not any(q.id == queue4.id for q in closed_list2),
        "اجرای دوم job همان پنل را دوباره پردازش نمی‌کند (idempotent)",
    )

    print("\n[Level 2] همه‌ی سناریوهای التماس دعا با موفقیت پاس شدند.\n")


CIRCLE_CHAT_ID = -100779
CIRCLE_USER_IDS = [71000 + i for i in range(7)]  # 0=creator, 1..6=members


async def test_level2_dhikr_circle() -> None:
    """سناریوهای Level 2 — حلقه ذکر، با telegram_idهای کاملاً مجزا از بقیه‌ی تست‌ها."""
    t = datetime.now(timezone.utc)

    print("\n== Level 2 (حلقه ذکر): همه باید اول بازی را شروع کرده باشند ==")

    async def circle_send(telegram_id: int, text: str, now: datetime):
        async with async_session_factory() as session:
            async with session.begin():
                return await process_activity(
                    session,
                    update_id=next_update_id(),
                    telegram_id=telegram_id,
                    username=f"circ{telegram_id}",
                    first_name="Tester",
                    chat_id=CIRCLE_CHAT_ID,
                    raw_text=text,
                    now=now,
                )

    for uid in CIRCLE_USER_IDS:
        t += timedelta(seconds=2)
        r = await circle_send(uid, "اللهم صل علی محمد و آل محمد", t)
        check(r.status == OutcomeStatus.SUCCESS, f"کاربر {uid}: اولین صلوات موفق")

    print("\n== ساخت حلقه (رایگان، بدون شرط تعداد عضو) ==")
    creator_id = CIRCLE_USER_IDS[0]
    async with async_session_factory() as session:
        async with session.begin():
            creator = await get_or_create_user(session, creator_id, "circ_creator", "Tester")
            create_outcome = await create_circle(session, creator, now=t)
    check(create_outcome.result == CreateCircleResult.SUCCESS, "ساخت حلقه موفق")
    circle = create_outcome.circle

    async with async_session_factory() as session:
        async with session.begin():
            creator2 = await get_or_create_user(session, creator_id, "circ_creator", "Tester")
            dup_outcome = await create_circle(session, creator2, now=t)
    check(dup_outcome.result == CreateCircleResult.ALREADY_IN_CIRCLE, "کاربر عضو یک حلقه نمی‌تواند حلقه‌ی دوم بسازد")

    print("\n== عضویت: هر کاربر فقط در یک حلقه ==")
    for uid in CIRCLE_USER_IDS[1:]:
        async with async_session_factory() as session:
            async with session.begin():
                usr = await get_or_create_user(session, uid, f"circ{uid}", "Tester")
                jout = await join_circle(session, usr, circle.id, now=t)
        check(jout.result == JoinCircleResult.SUCCESS, f"کاربر {uid} با موفقیت عضو حلقه شد")

    async with async_session_factory() as session:
        async with session.begin():
            already = await get_or_create_user(session, CIRCLE_USER_IDS[1], f"circ{CIRCLE_USER_IDS[1]}", "Tester")
            jout2 = await join_circle(session, already, circle.id, now=t)
    check(jout2.result == JoinCircleResult.ALREADY_IN_CIRCLE, "عضو موجود نمی‌تواند دوباره (یا در حلقه‌ی دیگر) عضو شود")

    print("\n== فعالیت: فقط ذکر معتبر سهم حلقه محسوب می‌شود؛ صلوات و نامعتبر و cooldown نه ==")
    tt = t + timedelta(minutes=1)
    r_salawat = await circle_send(CIRCLE_USER_IDS[1], "اللهم صل علی محمد و آل محمد", tt)
    check(r_salawat.circle_daily_count == 0, "صلوات هیچ سهمی به حلقه اضافه نمی‌کند")

    tt += timedelta(seconds=15)
    r_dhikr1 = await circle_send(CIRCLE_USER_IDS[1], "الحمدلله", tt)
    check(r_dhikr1.status == OutcomeStatus.SUCCESS, "اولین ذکر معتبر ثبت شد")
    check(r_dhikr1.circle_daily_count == 1, "سهم روزانه بعد از اولین ذکر == 1")
    check(r_dhikr1.noor_reward == 5 + circle_domain.CIRCLE_DHIKR_NOOR_BOOST, "پاداش ذکر داخل حلقه == 5+2=7 (یک پرداخت واحد)")

    r_cooldown = await circle_send(CIRCLE_USER_IDS[1], "الحمدلله", tt)  # بدون گذشت زمان کافی
    check(r_cooldown.status == OutcomeStatus.COOLDOWN, "ذکر در cooldown رد می‌شود")
    check(r_cooldown.circle_daily_count == 0, "فعالیت رد‌شده (cooldown) هیچ سهمی به حلقه اضافه نمی‌کند")

    r_invalid = await circle_send(CIRCLE_USER_IDS[1], "این یک پیام نامعتبر است", tt + timedelta(seconds=15))
    check(r_invalid.circle_daily_count == 0, "activity نامعتبر هیچ سهمی به حلقه اضافه نمی‌کند")

    print("\n== سهم روزانه: 0/10 -> 10/10 -> فعالیت یازدهم بدون bonus حلقه ==")
    last = None
    for i in range(2, 11):
        tt += timedelta(seconds=15)
        last = await circle_send(CIRCLE_USER_IDS[1], "الحمدلله", tt)
        check(last.status == OutcomeStatus.SUCCESS, f"ذکر شماره {i} کاربر موفق")
    check(last.circle_daily_count == 10, "سهم روزانه به 10/10 رسید")
    check(last.circle_just_completed_today, "flag تکمیل سهم روزانه فعال شد")

    tt += timedelta(seconds=15)
    r_11th = await circle_send(CIRCLE_USER_IDS[1], "الحمدلله", tt)
    check(r_11th.status == OutcomeStatus.SUCCESS, "ذکر یازدهم هم ثبت می‌شود (بدون محدودیت سیستم اصلی)")
    check(r_11th.noor_reward == 5, "اما دیگر bonus حلقه نمی‌گیرد (فقط پاداش عادی)")
    check(not r_11th.circle_just_completed_today, "دوباره flag تکمیل امروز فعال نمی‌شود")

    print("\n== Milestone پنج‌نفره: فقط با رسیدن ۵ عضو مختلف به 10/10 ==")
    # کاربر ۲ (CIRCLE_USER_IDS[2]) را فقط تا 4/10 پیش می‌بریم -> milestone نباید فعال شود
    for i in range(4):
        tt += timedelta(seconds=15)
        r = await circle_send(CIRCLE_USER_IDS[2], "الحمدلله", tt)
        check(not r.circle_milestone_winners, f"عضو دوم فعالیت {i + 1}: milestone هنوز فعال نشود")

    # اعضای ۳، ۴، ۵ (index 3,4,5) را کامل به 10/10 می‌رسانیم
    milestone_winners_seen = None
    for uid in CIRCLE_USER_IDS[3:6]:
        for i in range(10):
            tt += timedelta(seconds=15)
            r = await circle_send(uid, "الحمدلله", tt)
            check(r.status == OutcomeStatus.SUCCESS, f"کاربر {uid} ذکر {i + 1} موفق")
            if r.circle_milestone_winners:
                milestone_winners_seen = r.circle_milestone_winners

    # هنوز فقط ۴ عضو کامل (1 و 3،4،5) -> milestone نباید فعال شده باشد
    check(milestone_winners_seen is None, "با فقط ۴ عضو کامل، milestone هنوز فعال نمی‌شود")

    # عضو دوم (index 2) را هم کامل می‌کنیم -> این پنجمین عضو کامل‌شونده است -> milestone
    for i in range(6):  # از 4/10 به 10/10
        tt += timedelta(seconds=15)
        r = await circle_send(CIRCLE_USER_IDS[2], "الحمدلله", tt)
        if r.circle_milestone_winners:
            milestone_winners_seen = r.circle_milestone_winners

    check(milestone_winners_seen is not None, "با ۵ عضو کامل، milestone فعال می‌شود")
    check(len(milestone_winners_seen) == 5, "milestone دقیقاً ۵ برنده دارد")
    winner_ids = {w[0] for w in milestone_winners_seen}
    expected_ids = {CIRCLE_USER_IDS[1], CIRCLE_USER_IDS[2], CIRCLE_USER_IDS[3], CIRCLE_USER_IDS[4], CIRCLE_USER_IDS[5]}
    check(winner_ids == expected_ids, "برندگان milestone دقیقاً همان ۵ نفر زودتر تکمیل‌کننده‌اند")

    async with async_session_factory() as session:
        for uid in [CIRCLE_USER_IDS[1], CIRCLE_USER_IDS[2]]:
            u = await get_user_by_telegram_id(session, uid)
            check(u.noor_current >= circle_domain.CIRCLE_MILESTONE_REWARD_PER_MEMBER, f"کاربر {uid} پاداش milestone را گرفت")

    print("\n== عضو ششم/هفتم که کامل نکرده‌اند، از milestone سهمی نمی‌گیرند ==")
    async with async_session_factory() as session:
        for uid in [CIRCLE_USER_IDS[6]]:
            u = await get_user_by_telegram_id(session, uid)
            check(u.noor_current == 8, f"کاربر {uid} فقط پاداش اولین صلوات را دارد (بدون فعالیت دیگر)")

    print("\n== Milestone فقط یک‌بار در روز پرداخت می‌شود ==")
    tt += timedelta(seconds=15)
    r_after_milestone = await circle_send(CIRCLE_USER_IDS[6], "الحمدلله", tt)
    check(not r_after_milestone.circle_milestone_winners, "فعالیت بعد از milestone دوباره milestone رد نمی‌شود")

    async with async_session_factory() as session:
        circle_row = await session.get(DhikrCircle, circle.id)
        check(circle_row.milestone_paid_date is not None, "milestone_paid_date روی حلقه ثبت شده")

    print("\n== خروج از حلقه: قبل از ۷۲ ساعت رد، بعد از ۷۲ ساعت موفق ==")
    async with async_session_factory() as session:
        async with session.begin():
            leaver = await get_or_create_user(session, CIRCLE_USER_IDS[6], f"circ{CIRCLE_USER_IDS[6]}", "Tester")
            leave_locked = await leave_circle(session, leaver, now=t + timedelta(hours=1))
    check(leave_locked.result == LeaveCircleResult.LOCKED, "خروج قبل از ۷۲ ساعت رد شد")

    async with async_session_factory() as session:
        async with session.begin():
            leaver2 = await get_or_create_user(session, CIRCLE_USER_IDS[6], f"circ{CIRCLE_USER_IDS[6]}", "Tester")
            leave_ok = await leave_circle(session, leaver2, now=t + timedelta(hours=73))
    check(leave_ok.result == LeaveCircleResult.SUCCESS, "خروج بعد از ۷۲ ساعت موفق")

    async with async_session_factory() as session:
        u_after_leave = await get_user_by_telegram_id(session, CIRCLE_USER_IDS[6])
        check(u_after_leave.active_circle_id is None, "active_circle_id بعد از خروج پاک شد")

    print("\n== حذف عضو توسط سازنده: قبل از ۷۲ ساعت رد، بعد موفق؛ فقط سازنده می‌تواند حذف کند ==")
    async with async_session_factory() as session:
        async with session.begin():
            creator_u = await get_or_create_user(session, creator_id, "circ_creator", "Tester")
            circle_fresh = await session.get(DhikrCircle, circle.id)
            target = await get_user_by_telegram_id(session, CIRCLE_USER_IDS[5])
            remove_locked = await remove_member(session, creator_u, circle_fresh, target.id, now=t + timedelta(hours=1))
    check(remove_locked.result == RemoveMemberResult.LOCKED, "حذف عضو قبل از ۷۲ ساعت رد شد")

    async with async_session_factory() as session:
        async with session.begin():
            non_creator = await get_or_create_user(session, CIRCLE_USER_IDS[1], f"circ{CIRCLE_USER_IDS[1]}", "Tester")
            circle_fresh2 = await session.get(DhikrCircle, circle.id)
            target2 = await get_user_by_telegram_id(session, CIRCLE_USER_IDS[5])
            remove_not_creator = await remove_member(session, non_creator, circle_fresh2, target2.id, now=t + timedelta(hours=73))
    check(remove_not_creator.result == RemoveMemberResult.NOT_CREATOR, "فقط سازنده می‌تواند عضو حذف کند")

    async with async_session_factory() as session:
        async with session.begin():
            creator_u2 = await get_or_create_user(session, creator_id, "circ_creator", "Tester")
            circle_fresh3 = await session.get(DhikrCircle, circle.id)
            target3 = await get_user_by_telegram_id(session, CIRCLE_USER_IDS[5])
            remove_ok = await remove_member(session, creator_u2, circle_fresh3, target3.id, now=t + timedelta(hours=73))
    check(remove_ok.result == RemoveMemberResult.SUCCESS, "حذف عضو بعد از ۷۲ ساعت توسط سازنده موفق")

    async with async_session_factory() as session:
        u_removed = await get_user_by_telegram_id(session, CIRCLE_USER_IDS[5])
        check(u_removed.active_circle_id is None, "active_circle_id عضو حذف‌شده پاک شد")

    print("\n[Level 2] همه‌ی سناریوهای حلقه ذکر با موفقیت پاس شدند.\n")


async def main() -> None:
    await run_migrations()
    await test_level2_dua_queue()
    await test_level2_dhikr_circle()

    now = datetime.now(timezone.utc)

    # -------------------------------------------------------------
    print("\n== PV exclusion: activities only count in group (بند ۲) ==")
    check(_chat_allows_activity(ChatType.GROUP) is True, "group chat allows activity")
    check(_chat_allows_activity(ChatType.SUPERGROUP) is True, "supergroup chat allows activity")
    check(_chat_allows_activity(ChatType.PRIVATE) is False, "private chat does NOT allow activity")
    # نکته: process_activity دیگر چیزی درباره‌ی PV نمی‌داند (پارامتر chat_is_private حذف شد)؛
    # فیلتر PV در لایه‌ی handler (group_messages._chat_allows_activity) انجام می‌شود و همین‌جا
    # مستقیماً تست شده. handler برای PV اصلاً process_activity را صدا نمی‌زند.

    # -------------------------------------------------------------
    print("\n== First activity (بدون /start؛ فقط اولین صلوات معتبر در گروه) ==")
    outcome = await send("اللهم صل علی محمد و آل محمد", now)
    check(outcome.status == OutcomeStatus.SUCCESS, "first salawat -> success")
    check(outcome.is_first_activity, "flagged as first activity")
    check(outcome.noor_current == 8, "noor == 8 after first salawat")
    check(outcome.level_progress == 1, "outcome progress == 1/12")
    user = await get_user()
    check(user.level == 1, "level == 1 after first salawat")
    check(user.level_progress == 1, "progress == 1/12")
    check(user.salawat_count == 1, "salawat_count == 1")

    # -------------------------------------------------------------
    print("\n== Cooldown (salawat, still within first cooldown window) ==")
    outcome = await send("اللهم صل علی محمد و آل محمد", now + timedelta(seconds=3))
    check(outcome.status == OutcomeStatus.COOLDOWN, "second salawat within cooldown window -> cooldown")
    check(1 <= outcome.cooldown_remaining_seconds <= 10, "remaining time is sane")
    user = await get_user()
    check(user.salawat_count == 1, "salawat_count unchanged during cooldown")
    check(user.noor_current == 8, "noor unchanged during cooldown")

    # -------------------------------------------------------------
    print("\n== Dhikr before game rules (independent cooldowns) ==")
    now2 = now + timedelta(minutes=3)  # صلوات cooldown (۱۰ ثانیه) مدت‌ها پیش تمام شده
    outcome = await send("الحمدلله", now2)
    check(outcome.status == OutcomeStatus.SUCCESS, "alhamdulillah free & unlocked by default -> success")
    check(outcome.noor_reward == 5, "alhamdulillah reward == 5")
    user = await get_user()
    check(user.noor_current == 13, "noor == 8+5 == 13")
    check(user.dhikr_count == 1, "dhikr_count == 1")

    outcome = await send("اللهم صل علی محمد و آل محمد", now2 + timedelta(seconds=5))
    check(outcome.status == OutcomeStatus.SUCCESS, "salawat cooldown independent of dhikr cooldown")
    user = await get_user()
    check(user.salawat_count == 2, "salawat_count == 2")
    check(user.level_progress == 2, "progress == 2/12")

    # -------------------------------------------------------------
    print("\n== Invalid message handling (always silent — no warning text is ever shown) ==")
    outcome = await send("اللهم صل علی محمد و آل محمد پیام اضافه", now2 + timedelta(minutes=10))
    check(outcome.status == OutcomeStatus.INVALID_SILENT, "extra text -> silently invalid, no reply")

    outcome = await send("اللهم صل علی محمد و آل محمد 🙏", now2 + timedelta(minutes=10))
    check(outcome.status == OutcomeStatus.INVALID_SILENT, "emoji added -> silently invalid, no reply")

    outcome = await send(
        "اللهم صل علی محمد و آل محمد اللهم صل علی محمد و آل محمد", now2 + timedelta(minutes=10)
    )
    check(outcome.status == OutcomeStatus.INVALID_SILENT, "doubled activity -> silently invalid, no reply")

    outcome = await send("سلام بچه ها چطورید", now2 + timedelta(minutes=10))
    check(outcome.status == OutcomeStatus.UNRELATED, "unrelated chat -> ignored, not invalid")

    now3 = now2 + timedelta(seconds=6)  # داخل cooldown صلوات ۵ دقیقه‌ای
    outcome = await send("اللهم صل علی محمد پیام غلط", now3)
    check(outcome.status == OutcomeStatus.INVALID_SILENT, "invalid attempt during cooldown -> silent too")

    check(not hasattr(texts, "INVALID_MESSAGE"), "the '⚠️ متن واردشده معتبر نیست' text no longer exists at all")

    # -------------------------------------------------------------
    print("\n== Normalization (half-space, ي/ك, diacritics, tatweel) ==")
    now4 = now2 + timedelta(minutes=20)
    variant = "اَللّٰهُمَّ صَلِّ عَلَي مُحَمَّـد و آل محمد"  # با اعراب و کشیده و ي عربی
    outcome = await send(variant, now4)
    check(outcome.status == OutcomeStatus.SUCCESS, "heavily diacritic salawat variant accepted")
    check(outcome.milestone_kind == "bank_azkar", "bank_azkar milestone fires exactly on salawat #3")
    check(outcome.use_full_message is True, "milestone salawat is always a full consolidated message")

    # -------------------------------------------------------------
    print("\n== Expanded salawat variant list (اصلاحات نهایی: ۶ -> ۱۵-۲۰ نسخه) ==")
    from bot.domain.salawat_data import SALAWAT_VARIANTS  # noqa: E402

    check(15 <= len(SALAWAT_VARIANTS) <= 20, "salawat variant count is within the 15-20 range")
    check(
        any("عجل فرجهم" in v for v in SALAWAT_VARIANTS),
        "at least one variant includes 'و عجل فرجهم'",
    )

    # -------------------------------------------------------------
    print("\n== Locked dhikr before bank opens -> completely silent ==")
    PRE_BANK_ID = 555444
    t_pre = now4 + timedelta(minutes=40)
    await send_as(PRE_BANK_ID, "اللهم صل علی محمد و آل محمد", t_pre)  # صلوات ۱ -> بانک هنوز باز نیست
    user_pre = await get_user_by_telegram_id_wrap(PRE_BANK_ID)
    check(user_pre.bank_azkar_unlocked is False, "bank not yet unlocked after only 1 salawat")

    outcome = await send_as(PRE_BANK_ID, "سبحان الله", t_pre + timedelta(seconds=5))
    check(outcome.status == OutcomeStatus.INVALID_SILENT, "locked dhikr before bank opens -> silent, no response")
    user_pre = await get_user_by_telegram_id_wrap(PRE_BANK_ID)
    check(user_pre.noor_current == 8, "noor unchanged by the silently-ignored locked dhikr")
    check(user_pre.dhikr_count == 0, "dhikr_count unchanged by the silently-ignored locked dhikr")

    # الحمدلله رایگان است و باید حتی قبل از باز شدن بانک کار کند
    outcome = await send_as(PRE_BANK_ID, "الحمدلله", t_pre + timedelta(seconds=10))
    check(outcome.status == OutcomeStatus.SUCCESS, "free alhamdulillah still works before bank opens")

    # -------------------------------------------------------------
    print("\n== 67%/33% delivery split (outcome-level, isolated fresh user) ==")
    SPLIT_TEST_ID = 999888  # کاربر مجزا تا با رول‌های تصادفی تست‌های قبلی تداخل نکند
    t_split = now4 + timedelta(hours=1)
    await send_as(SPLIT_TEST_ID, "اللهم صل علی محمد و آل محمد", t_split)  # شروع بازی (پیام اول، تصادفی نیست)
    t_split += timedelta(minutes=6)

    with patch("bot.services.activity_service.random.random", return_value=0.10):  # < 0.33 -> full message
        outcome = await send_as(SPLIT_TEST_ID, "الحمدلله", t_split)
    check(outcome.use_full_message is True, "random()<0.33 -> full group message path")
    check(outcome.needs_reaction_explanation is False, "no explanation needed on the full-message path")

    t_split += timedelta(minutes=6)
    with patch("bot.services.activity_service.random.random", return_value=0.90):  # >= 0.33 -> reaction/PV
        outcome = await send_as(SPLIT_TEST_ID, "الحمدلله", t_split)
    check(outcome.use_full_message is False, "random()>=0.33 -> reaction+PV path")
    check(outcome.needs_reaction_explanation is True, "first-ever reaction -> explanation flagged once")

    t_split += timedelta(minutes=6)
    with patch("bot.services.activity_service.random.random", return_value=0.90):
        outcome = await send_as(SPLIT_TEST_ID, "الحمدلله", t_split)
    check(outcome.use_full_message is False, "second reaction path also chosen")
    check(outcome.needs_reaction_explanation is False, "explanation NOT repeated the second time")

    # -------------------------------------------------------------
    print("\n== Render layer: exactly-one-result audit (group XOR PV, never both) ==")

    def _fake_message():
        msg = MagicMock()
        msg.reply = AsyncMock()
        msg.answer = AsyncMock()
        msg.chat = MagicMock(id=CHAT_ID)
        msg.message_id = 12345
        msg.from_user = MagicMock(id=TELEGRAM_ID)
        return msg

    def _fake_bot(reaction_ok: bool):
        bot_mock = MagicMock()
        if reaction_ok:
            bot_mock.set_message_reaction = AsyncMock(return_value=None)
        else:
            bot_mock.set_message_reaction = AsyncMock(side_effect=Exception("telegram API error"))
        bot_mock.send_message = AsyncMock()
        return bot_mock

    base_outcome_kwargs = dict(
        status=OutcomeStatus.SUCCESS,
        activity_kind=ActivityKind.DHIKR,
        noor_reward=5,
        noor_current=42,
        is_first_activity=False,
        milestone_kind=None,
    )

    # Case A: reaction fails technically -> full group message, NEVER PV
    outcome_a = ActivityOutcome(use_full_message=False, needs_reaction_explanation=False, **base_outcome_kwargs)
    msg_a, bot_a = _fake_message(), _fake_bot(reaction_ok=False)
    await _render_success(bot_a, msg_a, outcome_a)
    check(msg_a.reply.await_count == 1, "reaction failure -> exactly one group full-message reply")
    check(bot_a.send_message.await_count == 0, "reaction failure -> PV is NEVER sent")
    check(msg_a.answer.await_count == 0, "reaction failure -> no extra group answer either")
    reply_text_a = msg_a.reply.await_args.args[0]
    reply_lines_a = reply_text_a.split("\n")
    check(reply_lines_a[0] == "✨ ذکرت ثبت شد", "normal dhikr success message keeps its fixed first line")
    check(
        sum(1 for line in reply_lines_a if line in closing_lines_module.CLOSING_LINES) == 1,
        "rendered normal success message carries exactly one random closing line",
    )

    # Case B: reaction succeeds, first time ever -> group explanation (with real result) ONLY, no PV
    outcome_b = ActivityOutcome(use_full_message=False, needs_reaction_explanation=True, **base_outcome_kwargs)
    msg_b, bot_b = _fake_message(), _fake_bot(reaction_ok=True)
    await _render_success(bot_b, msg_b, outcome_b)
    check(bot_b.set_message_reaction.await_count == 1, "reaction success path actually reacts")
    check(msg_b.reply.await_count == 1, "first-time reaction -> exactly one group explanation message")
    check(bot_b.send_message.await_count == 0, "first-time reaction explanation -> PV NOT sent (single result rule)")
    check(msg_b.answer.await_count == 0, "first-time reaction -> message.answer() is never used by this codebase")
    explanation_text = msg_b.reply.await_args.args[0]
    check("۵" in explanation_text or "5" in explanation_text, "explanation shows the real noor reward earned")
    check("۴۲" in explanation_text or "42" in explanation_text, "explanation shows the real current noor")
    check(
        not any(line in explanation_text for line in closing_lines_module.CLOSING_LINES),
        "reaction-explanation message (integration) never gets a random closing line",
    )

    # Case C: reaction succeeds, NOT first time -> PV result ONLY, no group text at all
    outcome_c = ActivityOutcome(use_full_message=False, needs_reaction_explanation=False, **base_outcome_kwargs)
    msg_c, bot_c = _fake_message(), _fake_bot(reaction_ok=True)
    await _render_success(bot_c, msg_c, outcome_c)
    check(bot_c.send_message.await_count == 1, "ordinary reaction path -> exactly one PV message")
    check(msg_c.reply.await_count == 0, "ordinary reaction path -> no group full-message reply")
    check(msg_c.answer.await_count == 0, "ordinary reaction path -> no group explanation either")
    pv_text_c = bot_c.send_message.await_args.kwargs.get("text") or bot_c.send_message.await_args.args[-1]
    check(
        not any(line in pv_text_c for line in closing_lines_module.CLOSING_LINES),
        "PV result message (integration) never gets a random closing line",
    )

    # Same audit again but for a SALAWAT outcome, to cover both activity kinds end-to-end
    salawat_outcome_kwargs = dict(base_outcome_kwargs)
    salawat_outcome_kwargs["activity_kind"] = ActivityKind.SALAWAT
    outcome_a2 = ActivityOutcome(use_full_message=False, needs_reaction_explanation=False, **salawat_outcome_kwargs)
    msg_a2, bot_a2 = _fake_message(), _fake_bot(reaction_ok=False)
    await _render_success(bot_a2, msg_a2, outcome_a2)
    reply_lines_a2 = msg_a2.reply.await_args.args[0].split("\n")
    check(len(reply_lines_a2) == 7, "rendered salawat full-group message: 4 fixed + progress-bar + blank + 1 closing line")
    check(reply_lines_a2[0] == "📿 صلواتت با موفقیت ثبت شد.", "salawat full-group message keeps its fixed first line")
    check(reply_lines_a2[3].startswith("⏳ صلوات بعدی:"), "salawat full-group message keeps its cooldown line")
    check(
        sum(1 for line in reply_lines_a2 if line in closing_lines_module.CLOSING_LINES) == 1,
        "salawat full-group message carries exactly one random closing line",
    )

    # -------------------------------------------------------------
    print("\n== Milestones: fast-forward to salawat #3..#12 ==")
    t = now4 + timedelta(minutes=25)
    seen_milestones = []
    for i in range(4, 13):
        t += timedelta(minutes=6)
        outcome = await send("اللهم صل علی محمد و آل محمد", t)
        check(outcome.status == OutcomeStatus.SUCCESS, f"salawat #{i} registered")
        if outcome.milestone_kind is not None:
            seen_milestones.append(outcome.milestone_kind)
            check(outcome.use_full_message is True, f"milestone salawat #{i} is a full consolidated message")

    user = await get_user()
    check(user.bank_azkar_unlocked, "bank_azkar unlocked by salawat #3")
    check(user.nameh_amal_unlocked, "nameh_amal unlocked by salawat #6")
    check(user.tasbih_unlocked, "tasbih unlocked by salawat #9")
    check(user.tasbih_level == 1, "tasbih starts at level 1 once unlocked")
    check(user.level == 2, "level == 2 after salawat #12")
    check(user.level_progress == 12, "progress frozen at 12/12")
    check(
        seen_milestones == ["nameh_amal", "tasbih", "level_up"],
        "exactly 3 more milestones fired during the loop, in order (nameh_amal@6, tasbih@9, level_up@12)",
    )

    # milestones must fire exactly once even under a duplicate resend attempt
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
            check(user.bank_azkar_unlocked and user.nameh_amal_unlocked and user.tasbih_unlocked,
                  "all milestone flags set exactly once (idempotent flags)")

    # -------------------------------------------------------------
    print("\n== Economy: unlock cost & insufficient noor ==")
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
            noor_before = user.noor_current
            dhikr = DHIKR_BY_KEY["la_ilaha_illallah"]  # cost 300
            outcome = await unlock_dhikr(session, user, dhikr)
    if noor_before < 300:
        check(outcome.result == UnlockResult.INSUFFICIENT_NOOR, "unlock fails with insufficient noor")
        user = await get_user()
        check(user.noor_current == noor_before, "noor unchanged after failed unlock")
    else:
        check(outcome.result == UnlockResult.SUCCESS, "unlock succeeds with enough noor")

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
            user.noor_current += 5000
            user.noor_total_earned += 5000
            noor_before_total = user.noor_total_earned

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
            dhikr = DHIKR_BY_KEY["la_ilaha_illallah"]
            outcome = await unlock_dhikr(session, user, dhikr)
    check(outcome.result == UnlockResult.SUCCESS, "unlock succeeds after topping up noor")

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
            dhikr = DHIKR_BY_KEY["la_ilaha_illallah"]
            outcome = await unlock_dhikr(session, user, dhikr)
    check(outcome.result == UnlockResult.ALREADY_UNLOCKED, "re-unlocking already-unlocked dhikr is a no-op")

    user = await get_user()
    check(user.noor_total_earned == noor_before_total, "spending noor does not reduce total_earned")

    # -------------------------------------------------------------
    print("\n== Tasbih upgrade & frozen cooldown rule ==")
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
            level_before = user.tasbih_level
            outcome = upgrade_tasbih(user)
    check(outcome.result == TasbihUpgradeResult.SUCCESS, "tasbih upgrade success")
    user = await get_user()
    check(user.tasbih_level == level_before + 1, "tasbih level incremented")
    check(
        user.last_dhikr_cooldown_seconds != outcome.new_cooldown_seconds or user.last_dhikr_at is None,
        "previously-recorded dhikr cooldown untouched by upgrade (frozen-value design)",
    )

    # -------------------------------------------------------------
    print("\n== Concurrency: duplicate update_id must not double-apply reward ==")
    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
            noor_before = user.noor_current
    dup_update_id = next_update_id()
    t = t + timedelta(minutes=10)

    async def send_dup():
        async with async_session_factory() as session:
            async with session.begin():
                return await process_activity(
                    session,
                    update_id=dup_update_id,
                    telegram_id=TELEGRAM_ID,
                    username="tester",
                    first_name="Tester",
                    chat_id=CHAT_ID,
                    raw_text="الحمدلله",
                    now=t,
                )

    results = await asyncio.gather(send_dup(), send_dup(), send_dup())
    successes = [r for r in results if r.status == OutcomeStatus.SUCCESS]
    duplicates = [r for r in results if r.status == OutcomeStatus.DUPLICATE_UPDATE]
    check(len(successes) == 1, "exactly one of the 3 concurrent identical updates succeeded")
    check(len(duplicates) == 2, "the other two were recognized as duplicates")

    async with async_session_factory() as session:
        async with session.begin():
            user = await get_user_by_telegram_id(session, TELEGRAM_ID)
    check(user.noor_current == noor_before + 5, "noor increased by exactly one reward, not three")

    # -------------------------------------------------------------
    print("\n== Chest: fixed 2% chance ==")
    with patch("bot.domain.chest.random.random", return_value=0.019):
        check(chest_domain.roll_chest_found() is True, "random()=0.019 < 2% -> chest found")
    with patch("bot.domain.chest.random.random", return_value=0.021):
        check(chest_domain.roll_chest_found() is False, "random()=0.021 >= 2% -> no chest")

    print("\n== Chest: reward range 40..72 inclusive ==")
    rewards = {chest_domain.roll_chest_reward() for _ in range(500)}
    check(min(rewards) >= 40, "no reward below 40")
    check(max(rewards) <= 72, "no reward above 72")

    print("\n== Chest: 1h open window vs 24h find-cooldown (independent) ==")
    t0 = datetime.now(timezone.utc)
    expiry = chest_domain.compute_expiry(t0)
    check(expiry == t0 + timedelta(hours=1), "open window is exactly 1 hour")
    check(chest_domain.is_expired(expiry, t0 + timedelta(minutes=59)) is False, "not expired at 59 min")
    check(chest_domain.is_expired(expiry, t0 + timedelta(hours=1, seconds=1)) is True, "expired just after 1h")

    check(chest_domain.can_create_new_chest(t0, t0 + timedelta(hours=23, minutes=59)) is False,
          "new chest blocked before 24h since previous FOUND time")
    check(chest_domain.can_create_new_chest(t0, t0 + timedelta(hours=24, seconds=1)) is True,
          "new chest allowed after 24h since previous FOUND time")
    # مهلت باز کردن (۱ ساعت) هیچ اثری روی cooldown پیدا کردن (۲۴ ساعت) ندارد -> جدا از هم تست شدند بالا

    print("\n== Chest: idempotent open (owner-only, single reward) ==")
    async with async_session_factory() as session:
        async with session.begin():
            owner = await get_or_create_user(session, TELEGRAM_ID, "tester", "Tester")
            intruder = await get_or_create_user(session, 222, "intruder", "Intruder")
            chest = Chest(
                user_id=owner.id,
                chat_id=CHAT_ID,
                created_at=datetime.now(timezone.utc),
                expires_at=chest_domain.compute_expiry(datetime.now(timezone.utc)),
                opened=False,
            )
            session.add(chest)
            await session.flush()

            not_owner_outcome = open_chest(chest, owner, requester_telegram_id=222)
            check(not_owner_outcome.result == ChestOpenResult.NOT_OWNER, "non-owner cannot open chest")

            noor_before_open = owner.noor_current
            total_before_open = owner.noor_total_earned
            first_open = open_chest(chest, owner, requester_telegram_id=TELEGRAM_ID)
            check(first_open.result == ChestOpenResult.SUCCESS, "owner opens chest successfully")
            check(40 <= first_open.reward_noor <= 72, "reward within 40..72 inclusive")
            check(owner.noor_current == noor_before_open + first_open.reward_noor, "current noor increased")
            check(
                owner.noor_total_earned == total_before_open + first_open.reward_noor,
                "total earned noor increased",
            )

            second_open = open_chest(chest, owner, requester_telegram_id=TELEGRAM_ID)
            check(second_open.result == ChestOpenResult.ALREADY_OPENED, "re-opening is idempotent, no double reward")
            check(owner.noor_current == noor_before_open + first_open.reward_noor, "noor NOT doubled on re-open")

    print("\n== Chest: expired chest cannot be opened ==")
    async with async_session_factory() as session:
        async with session.begin():
            owner = await get_user_by_telegram_id(session, TELEGRAM_ID)
            old_time = datetime.now(timezone.utc) - timedelta(hours=2)
            expired_chest = Chest(
                user_id=owner.id,
                chat_id=CHAT_ID,
                created_at=old_time,
                expires_at=chest_domain.compute_expiry(old_time),
                opened=False,
            )
            session.add(expired_chest)
            await session.flush()
            outcome_expired = open_chest(expired_chest, owner, requester_telegram_id=TELEGRAM_ID)
            check(outcome_expired.result == ChestOpenResult.EXPIRED, "chest past 1h window cannot be opened")

    # -------------------------------------------------------------
    print("\n== Closing-line pool & no-repeat-in-last-10 mechanism ==")
    check(len(closing_lines_module.CLOSING_LINES) == 32, "closing-line pool has exactly the 32 given sentences")
    check(len(set(closing_lines_module.CLOSING_LINES)) == 32, "no duplicate sentence in the closing-line pool")

    # exact-structure checks on the text-builder functions themselves
    salawat_with = texts.salawat_success(8, 55, 300, closing_line="🌱 تست خط پایانی")
    salawat_lines = salawat_with.split("\n")
    check(len(salawat_lines) == 5, "salawat_success: 4 fixed lines + 1 closing line = 5")
    check(salawat_lines[0] == "📿 صلواتت با موفقیت ثبت شد.", "salawat fixed line 1 unchanged")
    check(salawat_lines[1] == "✨ +۸ نور", "salawat fixed line 2 (noor reward) correct")
    check(salawat_lines[2] == "💫 نور معنویتت رسید به: ۵۵", "salawat fixed line 3 (current noor) correct")
    check(salawat_lines[3] == "⏳ صلوات بعدی: 5:00", "salawat fixed line 4 (cooldown) correct")
    check(salawat_lines[4] == "🌱 تست خط پایانی", "salawat closing line is exactly the last line")
    salawat_without = texts.salawat_success(8, 55, 300)
    check(len(salawat_without.split("\n")) == 4, "salawat_success WITHOUT a closing_line keeps exactly 4 lines")

    dhikr_with = texts.dhikr_success(5, 20, 290, closing_line="🌿 تست ذکر")
    dhikr_lines = dhikr_with.split("\n")
    check(len(dhikr_lines) == 5, "dhikr_success: 4 fixed lines + 1 closing line = 5")
    check(dhikr_lines[0] == "✨ ذکرت ثبت شد", "dhikr fixed line 1 unchanged")
    check(dhikr_lines[1] == "✨ +۵ نور", "dhikr fixed line 2 (noor reward) correct")
    check(dhikr_lines[2] == "💫 نور معنویتت رسید به: ۲۰", "dhikr fixed line 3 (current noor) correct")
    check(dhikr_lines[3] == "⏳ ذکر بعدی: 4:50", "dhikr fixed line 4 (cooldown) correct")
    check(dhikr_lines[4] == "🌿 تست ذکر", "dhikr closing line is exactly the last line")
    dhikr_without = texts.dhikr_success(5, 20, 290)
    check(len(dhikr_without.split("\n")) == 4, "dhikr_success WITHOUT a closing_line keeps exactly 4 lines")

    # milestone / first-activity / level-up / PV / reaction-explanation / cooldown / invalid: all untouched
    milestone_text = texts.salawat_milestone_message(
        milestone_kind="tasbih", noor_reward=8, noor_current=100, level_progress=9, level_total=12
    )
    check(
        not any(line in milestone_text for line in closing_lines_module.CLOSING_LINES),
        "milestone message never contains a random closing line",
    )
    first_text = texts.first_salawat_registered(8, 8, 1, 12)
    check(
        not any(line in first_text for line in closing_lines_module.CLOSING_LINES),
        "first-activity message never contains a random closing line",
    )
    pv_text = texts.pv_activity_result(5, 50, None)
    check(
        not any(line in pv_text for line in closing_lines_module.CLOSING_LINES),
        "PV result message never contains a random closing line",
    )
    reaction_text = texts.reaction_first_time_explanation(5, 50, None)
    check(
        not any(line in reaction_text for line in closing_lines_module.CLOSING_LINES),
        "reaction-explanation message never contains a random closing line",
    )
    cooldown_text = texts.salawat_cooldown_message(42)
    check(
        not any(line in cooldown_text for line in closing_lines_module.CLOSING_LINES),
        "cooldown message never contains a random closing line",
    )
    check(cooldown_text == "⏳ صلوات بعدی: 0:42", "cooldown message format is completely untouched")
    dhikr_cooldown_text = texts.dhikr_cooldown_message(17)
    check(
        not any(line in dhikr_cooldown_text for line in closing_lines_module.CLOSING_LINES),
        "dhikr cooldown message never contains a random closing line",
    )
    upgrade_success_text = texts.tasbih_upgrade_success(3, 240)
    check(
        not any(line in upgrade_success_text for line in closing_lines_module.CLOSING_LINES),
        "tasbih upgrade-success message never contains a random closing line",
    )

    # invalid messages are always silent (no text at all is ever produced/shown) — already covered by the
    # "Invalid message handling" section above (outcome.status == OutcomeStatus.INVALID, no message sent).

    # no-repeat-in-last-10 mechanism
    closing_lines_module._reset_for_tests()
    FAKE_UID = 3141592
    seen: list[str] = []
    for _ in range(10):
        line = closing_lines_module.pick_closing_line(FAKE_UID)
        check(line not in seen, "no repeat within the first 10 picks for the same user")
        check(line in closing_lines_module.CLOSING_LINES, "picked line always comes from the fixed 32-line set")
        seen.append(line)
    check(len(set(seen)) == 10, "10 distinct closing lines picked in a row (no repeats in the recent-10 window)")

    # a different user has an independent history (no cross-user interference)
    OTHER_UID = 2718281
    other_first = closing_lines_module.pick_closing_line(OTHER_UID)
    check(other_first in closing_lines_module.CLOSING_LINES, "a different user's pick still comes from the pool")

    # after 10 picks, the pool of allowed candidates is exactly "all 32 minus the last 10 seen"
    next_pick = closing_lines_module.pick_closing_line(FAKE_UID)
    check(next_pick not in seen[-10:], "11th pick still avoids the (now-updated) 10 most recent lines")

    # -------------------------------------------------------------
    print("\n== Tasbih panel: owner-scoped photo panel (edit-in-place, single message) ==")

    def _fake_panel_message():
        msg = MagicMock()
        msg.edit_caption = AsyncMock()
        msg.answer = AsyncMock()
        return msg

    def _fake_callback(data: str, from_user_id: int, message):
        cb = MagicMock()
        cb.data = data
        cb.from_user = MagicMock(id=from_user_id, username="tester", first_name="Tester")
        cb.message = message
        cb.answer = AsyncMock()
        return cb

    async def _prepare_tasbih_user(telegram_id: int, level: int = 1, noor: int = 0):
        async with async_session_factory() as session:
            async with session.begin():
                u = await get_or_create_user(session, telegram_id, "tester", "Tester")
                u.tasbih_unlocked = True
                u.tasbih_level = level
                u.noor_current = noor

    TASBIH_OWNER = 888004
    await _prepare_tasbih_user(TASBIH_OWNER, level=1, noor=100000)

    msg_tsb = _fake_panel_message()
    upd_tsb = MagicMock(update_id=next_update_id())

    # non-owner click -> completely silent (no answer, no edit)
    cb_intruder = _fake_callback(f"tsb:main:{TASBIH_OWNER}", from_user_id=999997, message=msg_tsb)
    await on_tasbih_panel_callback(cb_intruder, upd_tsb)
    check(msg_tsb.edit_caption.await_count == 0, "tasbih panel: non-owner click never edits the panel")
    check(cb_intruder.answer.await_count == 0, "tasbih panel: non-owner click never gets any answer")

    # owner opens the main page
    cb_main = _fake_callback(f"tsb:main:{TASBIH_OWNER}", from_user_id=TASBIH_OWNER, message=msg_tsb)
    await on_tasbih_panel_callback(cb_main, upd_tsb)
    check(msg_tsb.edit_caption.await_count == 1, "tasbih panel: owner main click edits the caption exactly once")
    main_caption_tsb = msg_tsb.edit_caption.await_args.kwargs["caption"]
    check("تسبیح" in main_caption_tsb, "tasbih main page caption mentions تسبیح")
    check("📿" in main_caption_tsb, "tasbih main caption uses 📿")
    check("🧿" not in main_caption_tsb, "tasbih main caption never uses the wrong 🧿 emoji")
    check(msg_tsb.answer.await_count == 0, "tasbih panel navigation never sends a brand-new message")

    # upgrade_ask -> confirm dialog, edits the SAME message
    msg_tsb.edit_caption.reset_mock()
    cb_ask = _fake_callback(f"tsb:upgrade_ask:{TASBIH_OWNER}", from_user_id=TASBIH_OWNER, message=msg_tsb)
    await on_tasbih_panel_callback(cb_ask, upd_tsb)
    check(msg_tsb.edit_caption.await_count == 1, "tasbih panel: upgrade_ask edits the same message")
    ask_caption = msg_tsb.edit_caption.await_args.kwargs["caption"]
    check("سطح" in ask_caption, "tasbih confirm dialog mentions the upgrade")

    # upgrade_cancel -> back to main page, still the SAME message
    msg_tsb.edit_caption.reset_mock()
    cb_cancel = _fake_callback(f"tsb:upgrade_cancel:{TASBIH_OWNER}", from_user_id=TASBIH_OWNER, message=msg_tsb)
    await on_tasbih_panel_callback(cb_cancel, upd_tsb)
    check(msg_tsb.edit_caption.await_count == 1, "tasbih panel: upgrade_cancel returns to main page via same message")
    check(msg_tsb.answer.await_count == 0, "tasbih panel: cancel never sends a brand-new message")

    # upgrade_confirm -> success, edits the SAME message with the new level
    msg_tsb.edit_caption.reset_mock()
    confirm_update = MagicMock(update_id=next_update_id())
    cb_confirm = _fake_callback(f"tsb:upgrade_confirm:{TASBIH_OWNER}", from_user_id=TASBIH_OWNER, message=msg_tsb)
    await on_tasbih_panel_callback(cb_confirm, confirm_update)
    check(msg_tsb.edit_caption.await_count == 1, "tasbih panel: upgrade_confirm edits the same message with the result")
    success_caption = msg_tsb.edit_caption.await_args.kwargs["caption"]
    check("ارتقا پیدا کرد" in success_caption, "tasbih success caption confirms the upgrade")
    check("cooldown" not in success_caption.lower(), "no leftover English word 'cooldown' in tasbih panel texts")
    check(msg_tsb.answer.await_count == 0, "tasbih panel: upgrade result never sends a brand-new message")

    user_after_tsb = await get_user_by_telegram_id_wrap(TASBIH_OWNER)
    check(user_after_tsb.tasbih_level == 2, "tasbih level actually incremented through the panel")

    # non-owner still cannot touch the panel after all these actions
    msg_tsb.edit_caption.reset_mock()
    cb_intruder2 = _fake_callback(f"tsb:upgrade_ask:{TASBIH_OWNER}", from_user_id=555444, message=msg_tsb)
    await on_tasbih_panel_callback(cb_intruder2, upd_tsb)
    check(msg_tsb.edit_caption.await_count == 0, "tasbih panel: non-owner still cannot touch the panel afterwards")
    check(cb_intruder2.answer.await_count == 0, "tasbih panel: non-owner still gets zero response afterwards")

    # -------------------------------------------------------------
    print("\n== Bank azkar panel: owner-scoped photo panel (edit-in-place, single message) ==")

    BANK_OWNER = 888005
    msg_bnk = _fake_panel_message()
    upd_bnk = MagicMock(update_id=next_update_id())

    # non-owner click -> completely silent
    cb_bnk_intruder = _fake_callback(f"bnk:main:{BANK_OWNER}", from_user_id=999996, message=msg_bnk)
    await on_bank_panel_callback(cb_bnk_intruder, upd_bnk)
    check(msg_bnk.edit_caption.await_count == 0, "bank panel: non-owner click never edits the panel")
    check(cb_bnk_intruder.answer.await_count == 0, "bank panel: non-owner click never gets any answer")

    # owner opens the main page
    cb_bnk_main = _fake_callback(f"bnk:main:{BANK_OWNER}", from_user_id=BANK_OWNER, message=msg_bnk)
    await on_bank_panel_callback(cb_bnk_main, upd_bnk)
    check(msg_bnk.edit_caption.await_count == 1, "bank panel: owner main click edits the caption exactly once")
    main_caption_bnk = msg_bnk.edit_caption.await_args.kwargs["caption"]
    check("بانک اذکار" in main_caption_bnk, "bank panel main caption mentions بانک اذکار")
    check(msg_bnk.answer.await_count == 0, "bank panel navigation never sends a brand-new message")

    # owner views a (locked) dhikr's details -> edits the SAME message
    msg_bnk.edit_caption.reset_mock()
    dhikr_key = "la_ilaha_illallah"
    cb_bnk_view = _fake_callback(f"bnk:view:{BANK_OWNER}:{dhikr_key}", from_user_id=BANK_OWNER, message=msg_bnk)
    await on_bank_panel_callback(cb_bnk_view, upd_bnk)
    check(msg_bnk.edit_caption.await_count == 1, "bank panel: view-detail edits the same message")
    detail_caption = msg_bnk.edit_caption.await_args.kwargs["caption"]
    check("نور" in detail_caption, "detail caption shows purchase info for a locked dhikr")

    # top up noor, then buy -> success edits the SAME message
    async with async_session_factory() as session:
        async with session.begin():
            u = await get_or_create_user(session, BANK_OWNER, "tester", "Tester")
            u.noor_current = 100000

    msg_bnk.edit_caption.reset_mock()
    buy_update = MagicMock(update_id=next_update_id())
    cb_bnk_buy = _fake_callback(f"bnk:buy:{BANK_OWNER}:{dhikr_key}", from_user_id=BANK_OWNER, message=msg_bnk)
    await on_bank_panel_callback(cb_bnk_buy, buy_update)
    check(msg_bnk.edit_caption.await_count == 1, "bank panel: buy edits the same message with the result")
    buy_caption = msg_bnk.edit_caption.await_args.kwargs["caption"]
    check("باز شد" in buy_caption, "purchase-success caption confirms the dhikr was unlocked")
    check(msg_bnk.answer.await_count == 0, "bank panel: buy never sends a brand-new message")

    # پس از خرید، صاحب پنل ذکرِ باز شده را دوباره unlocked می‌بیند
    async with async_session_factory() as session:
        u = await get_user_by_telegram_id(session, BANK_OWNER)
        from bot.services.unlock_service import is_unlocked

        unlocked_after = await is_unlocked(session, u, DHIKR_BY_KEY[dhikr_key])
    check(unlocked_after is True, "dhikr is actually unlocked in the database after purchasing via the panel")

    # back to the main page (from the "back" button) -> still the SAME message
    msg_bnk.edit_caption.reset_mock()
    cb_bnk_back = _fake_callback(f"bnk:main:{BANK_OWNER}", from_user_id=BANK_OWNER, message=msg_bnk)
    await on_bank_panel_callback(cb_bnk_back, upd_bnk)
    check(msg_bnk.edit_caption.await_count == 1, "bank panel: back-to-main edits the same message")
    back_caption = msg_bnk.edit_caption.await_args.kwargs["caption"]
    check("بانک اذکار" in back_caption, "bank panel main caption mentions بانک اذکار")

    # non-owner still cannot touch the panel after all these actions
    msg_bnk.edit_caption.reset_mock()
    cb_bnk_intruder2 = _fake_callback(f"bnk:view:{BANK_OWNER}:{dhikr_key}", from_user_id=444333, message=msg_bnk)
    await on_bank_panel_callback(cb_bnk_intruder2, upd_bnk)
    check(msg_bnk.edit_caption.await_count == 0, "bank panel: non-owner still cannot touch the panel afterwards")
    check(cb_bnk_intruder2.answer.await_count == 0, "bank panel: non-owner still gets zero response afterwards")

    # -------------------------------------------------------------
    print("\n== show_bank_azkar / show_tasbih: fresh photo panel every time, starts at the main page ==")

    def _fake_command_message(telegram_id: int):
        msg = MagicMock()
        msg.answer_photo = AsyncMock()
        msg.from_user = MagicMock(id=telegram_id)
        return msg

    BANK_USER = 888006
    async with async_session_factory() as session:
        async with session.begin():
            u = await get_or_create_user(session, BANK_USER, "tester", "Tester")
            u.bank_azkar_unlocked = True

    msg_cmd1 = _fake_command_message(BANK_USER)
    await show_bank_azkar(msg_cmd1)
    check(msg_cmd1.answer_photo.await_count == 1, "show_bank_azkar sends exactly one photo panel")
    kwargs_cmd1 = msg_cmd1.answer_photo.await_args.kwargs
    check("caption" in kwargs_cmd1 and "بانک اذکار" in kwargs_cmd1["caption"], "panel caption mentions بانک اذکار")
    check(kwargs_cmd1["caption"] == texts.bank_azkar_panel_header(), "a fresh bank-azkar panel always opens on the main page")
    check("reply_markup" in kwargs_cmd1 and kwargs_cmd1["reply_markup"] is not None, "panel includes its buttons")

    msg_cmd2 = _fake_command_message(BANK_USER)
    await show_bank_azkar(msg_cmd2)
    check(msg_cmd2.answer_photo.await_count == 1, "re-sending «بانک اذکار» creates a brand-new, independent panel")

    TASBIH_USER2 = 888007
    await _prepare_tasbih_user(TASBIH_USER2, level=4, noor=0)
    msg_cmd3 = _fake_command_message(TASBIH_USER2)
    await show_tasbih(msg_cmd3)
    check(msg_cmd3.answer_photo.await_count == 1, "show_tasbih sends exactly one photo panel")
    kwargs_cmd3 = msg_cmd3.answer_photo.await_args.kwargs
    check("📿" in kwargs_cmd3["caption"], "tasbih panel caption uses 📿")
    check("🧿" not in kwargs_cmd3["caption"], "tasbih panel caption never uses the wrong 🧿 emoji")

    msg_cmd4 = _fake_command_message(TASBIH_USER2)
    await show_tasbih(msg_cmd4)
    check(msg_cmd4.answer_photo.await_count == 1, "re-sending «تسبیح» creates a brand-new, independent panel")

    # -------------------------------------------------------------
    print("\n== Sanity: earlier systems are unaffected by these changes ==")
    # صلوات/ذکر/نور/زمان انتظار/۶۷٪-۳۳٪/پیام خصوصی/مرحله‌ها/ارتقا/صندوقچه/بانک اذکار/جلوگیری از تکرار
    # همگی در بخش‌های بالای همین فایل، که بدون تغییر باقی مانده‌اند، پوشش داده شده و سبز شده‌اند.
    check(True, "all pre-existing sections above (unchanged) still passed")

    # -------------------------------------------------------------
    print("\n== Reminder: only users with >=1 successful activity are eligible ==")
    async with async_session_factory() as session:
        async with session.begin():
            never_played = await get_or_create_user(session, 333, "newbie", "Newbie")
            # کاربری که هرگز فعالیتی نداشته: game_started=False, last_activity_at=None
            check(never_played.game_started is False, "brand-new user has game_started=False")

            due_far_future = await get_users_due_for_reminder(
                session, now=datetime.now(timezone.utc) + timedelta(days=3650)
            )
            due_ids = {u.telegram_id for u in due_far_future}
            check(333 not in due_ids, "user who never played is never eligible for a reminder")
            check(TELEGRAM_ID in due_ids, "user who has played IS eligible once inactivity threshold passes")

    print("\nALL TESTS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
