"""
پنل «مسیر انتظار» (سطح ۱): نماز اول وقت، دروس و آزمون.

مثل پنل‌های بانک/شغل، هر بار «مسیر انتظار» یک پنل مستقل می‌سازد؛ owner_id داخل callback_data است و
کلیک بقیه کاملاً بی‌پاسخ می‌ماند.

callback_data پنل (در گروه یا PV):   pth:<action>:<owner_id>[:arg]
  home | pray | first | open:<prayer> | locked:<prayer> | claim:<prayer> | claimed
  loc:<page> | setcity:<city_key>      (موقعیت مکانی / انتخاب شهر)
  lessons | lesson:<n> | heard:<n> | soon | exam:<n>
callback_data جواب سؤال آزمون (فقط در PV):   exq:<exam_id>:<position>:<option>
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    Update,
)

from bot.config import settings

from bot.database.engine import async_session_factory
from bot.domain import cities_data as cd
from bot.domain import lessons_data as ld
from bot.domain import prayer_times as pt
from bot.services import lesson_service as ls
from bot.services import prayer_service as ps
from bot.services.idempotency import try_claim_update
from bot.services.user_service import get_or_create_user, get_user_by_telegram_id
from bot.texts import path_texts as tx

logger = logging.getLogger(__name__)
router = Router(name="path_panel")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _audio_url_for(lesson_no: int) -> str | None:
    """لینک پست صوتی کانال برای درس (یا None اگر تنظیم نشده/هنوز مقدار نمونه است)."""
    url = {1: settings.lesson1_audio_url, 2: settings.lesson2_audio_url}.get(lesson_no, "")
    if not url:
        return None
    if "YourChannel" in url:
        logger.warning("لینک صوتی درس %s هنوز مقدار نمونه است", lesson_no)
        return None
    return url


def _btn(text: str, owner_id: int, action: str, *args: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=":".join(["pth", action, str(owner_id), *args]))


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# صفحه‌ها
# ---------------------------------------------------------------------------


def page_home(owner_id: int):
    return tx.PATH_HOME, _kb([[_btn("🕌 نماز", owner_id, "pray")]])


def page_pray(owner_id: int):
    return tx.PATH_PRAYER_MENU, _kb(
        [
            [_btn("🌅 نماز اول وقت", owner_id, "first")],
            [_btn("📍 موقعیت مکانی", owner_id, "loc", "0")],
            [_btn("📚 دروس", owner_id, "lessons")],
            [_btn("🔙 مسیر انتظار", owner_id, "home")],
        ]
    )


async def page_first(session, user, owner_id: int, now: datetime, timings):
    views = await ps.get_prayer_views(session, user, now, timings)
    rows: list[list[InlineKeyboardButton]] = []
    if views is not None:
        for v in views:
            if v.claimed:
                action = "claimed"
            elif v.state == pt.WindowState.OPEN:
                action = "open"
            else:
                action = "locked"
            rows.append([_btn(tx.prayer_button_label(v), owner_id, action, v.prayer.key)])
    rows.append([_btn("🔙 نماز", owner_id, "pray")])
    return tx.first_time_page(views, city_name=ps.city_for_user(user).name), _kb(rows)


def page_location(user, owner_id: int, page: int):
    """فهرست شهرها (دو ستونه، صفحه‌بندی‌شده)؛ شهر فعلی با ✅ مشخص می‌شود."""
    page = cd.clamp_page(page)
    current = ps.city_for_user(user)
    cities = cd.cities_on_page(page)
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(cities), 2):
        rows.append(
            [
                _btn(tx.city_button_label(c.name, c.key == current.key), owner_id, "setcity", c.key)
                for c in cities[i : i + 2]
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_btn("◀️ قبلی", owner_id, "loc", str(page - 1)))
    if page < cd.page_count() - 1:
        nav.append(_btn("بعدی ▶️", owner_id, "loc", str(page + 1)))
    if nav:
        rows.append(nav)
    rows.append([_btn("🔙 نماز", owner_id, "pray")])
    return tx.location_page(current.name, page, cd.page_count()), _kb(rows)


async def page_lessons(user, owner_id: int):
    rows = [
        [
            _btn(
                tx.lesson_button_label(lesson, ls.is_lesson_passed(user, lesson.number)),
                owner_id,
                "lesson" if lesson.available else "soon",
                str(lesson.number),
            )
        ]
        for lesson in ld.LESSONS
    ]
    rows.append([_btn("🔙 نماز", owner_id, "pray")])
    return tx.lessons_page(bool(user.lesson1_passed), bool(user.lesson2_passed)), _kb(rows)


def page_lesson(user, owner_id: int, lesson: ld.Lesson, now: datetime):
    passed = ls.is_lesson_passed(user, lesson.number)
    # درس‌هایی که شنیدنشان شرط است (درس ۱): تا «شنیدم» نزده، فقط دکمه‌ی «شنیدم» نشان داده می‌شود
    # و دکمه‌ی آزمون بعد از آن می‌آید.
    heard = ls.is_heard(user, lesson.number)
    rows: list[list[InlineKeyboardButton]] = []
    if not passed:
        if not heard:
            rows.append([_btn(tx.HEARD_BUTTON_LABEL, owner_id, "heard", str(lesson.number))])
        else:
            rows.append([_btn("📝 آزمون", owner_id, "exam", str(lesson.number))])
    rows.append([_btn("🔙 دروس", owner_id, "lessons")])
    wait = 0 if (passed or not heard) else ls.retry_remaining_seconds(user, now)
    return tx.lesson_page(lesson, passed, wait, heard), _kb(rows)


# ---------------------------------------------------------------------------
# دستور متنی «مسیر انتظار»
# ---------------------------------------------------------------------------


async def show_path_panel(message: Message) -> None:
    if message.from_user is None:
        return
    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        # قابلیت برای کسی که بازی را شروع نکرده باز نمی‌شود (و لو هم نمی‌رود).
        if user is None or not user.game_started:
            return
    text, kb = page_home(message.from_user.id)
    await message.reply(text, reply_markup=kb)


async def _edit(
    callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup, audio_url: str | None = None
) -> None:
    """audio_url: لینک پست صوتی کانال؛ پلیر صوتی زیر متن همین پیام نمایش داده می‌شود."""
    preview = (
        LinkPreviewOptions(url=audio_url, show_above_text=False, prefer_large_media=True)
        if audio_url
        else LinkPreviewOptions(is_disabled=True)
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb, link_preview_options=preview)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        logger.warning("edit_text failed, sending new message instead: %s", exc)
        try:
            await callback.message.answer(text, reply_markup=kb, link_preview_options=preview)
        except Exception:  # noqa: BLE001
            logger.exception("ارسال پیام جایگزین هم ناموفق بود")


async def _send_one_media(bot, chat_id: int, media: ld.LessonMedia) -> None:
    """file_id تلگرام اولویت دارد؛ وگرنه فایل محلی. اگر نوع فایل با kind نخواند، به‌صورت document می‌رود."""
    if media.file_id:
        source = media.file_id
    else:
        path = _PROJECT_ROOT / media.path
        if not path.is_file():
            raise FileNotFoundError(path)
        source = FSInputFile(path)
    caption = media.caption or None
    senders = {"audio": bot.send_audio, "video": bot.send_video}
    primary = senders.get(media.kind, bot.send_document)
    try:
        await primary(chat_id, source, caption=caption)
    except TelegramBadRequest:
        if primary is bot.send_document:
            raise
        await bot.send_document(chat_id, source, caption=caption)


async def _send_lesson_media(bot, chat_id: int, lesson: ld.Lesson) -> None:
    for media in lesson.media:
        try:
            await _send_one_media(bot, chat_id, media)
        except Exception:  # noqa: BLE001
            logger.exception("ارسال فایل درس ناموفق بود: %s", media.file_id[:12] or media.path)
            try:
                await bot.send_message(chat_id, tx.LESSON_MEDIA_FAILED)
            except Exception:  # noqa: BLE001
                logger.debug("اطلاع خطای فایل هم ارسال نشد", exc_info=True)


# ---------------------------------------------------------------------------
# کلیک‌های پنل
# ---------------------------------------------------------------------------


@router.callback_query(lambda c: c.data and c.data.startswith("pth:"))
async def on_path_callback(callback: CallbackQuery, event_update: Update) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
        return
    action, owner_id, args = parts[1], int(parts[2]), parts[3:]
    if callback.from_user.id != owner_id:
        return

    now = datetime.now(timezone.utc)
    # دریافت اوقات شرعی از شبکه، بیرون از تراکنش دیتابیس.
    timings = None
    if action in ("first", "open", "claim", "locked"):
        async with async_session_factory() as read_session:
            city = ps.city_for_user(await get_user_by_telegram_id(read_session, owner_id))
        timings = await ps.get_today_timings(now, city)

    toast: str | None = None
    alert = False
    page = None
    media_lesson: ld.Lesson | None = None
    audio_lesson: ld.Lesson | None = None  # صفحه‌ی درسِ دارای فایل صوتی (برای حفظ پلیر کانال)
    exam_start: tuple[str, object] | None = None  # ("ok", exam) | ("toast", text)

    async with async_session_factory() as session:
        async with session.begin():
            if not await try_claim_update(session, event_update.update_id):
                await callback.answer()
                return
            user = await get_or_create_user(
                session, owner_id, callback.from_user.username, callback.from_user.first_name
            )

            if action == "home":
                page = page_home(owner_id)

            elif action == "pray":
                page = page_pray(owner_id)

            elif action == "first":
                page = await page_first(session, user, owner_id, now, timings)

            elif action == "loc":
                page = page_location(user, owner_id, int(args[0]) if args and args[0].isdigit() else 0)

            elif action == "setcity" and args:
                city = cd.get_city(args[0])
                if city is None:
                    toast, alert = tx.CITY_UNKNOWN, True
                    page = page_location(user, owner_id, 0)
                else:
                    user.prayer_city = city.key
                    toast = tx.city_selected_toast(city.name)
                    page = page_pray(owner_id)

            elif action in ("open", "locked") and args:
                views = await ps.get_prayer_views(session, user, now, timings)
                view = next((v for v in views or [] if v.prayer.key == args[0]), None)
                if views is None:
                    toast, alert = tx.PRAYER_UNAVAILABLE, True
                elif view is None:
                    page = await page_first(session, user, owner_id, now, timings)
                elif view.claimed:
                    toast = tx.PRAYER_ALREADY_CLAIMED
                    page = await page_first(session, user, owner_id, now, timings)
                elif view.state != pt.WindowState.OPEN:
                    toast = tx.prayer_locked_toast(view.prayer, view.adhan_at, view.state)
                    alert = True
                    page = await page_first(session, user, owner_id, now, timings)
                else:
                    page = (
                        tx.prayer_open_page(view),
                        _kb(
                            [
                                [_btn(f"🤲 {view.prayer.confirm_label}", owner_id, "claim", view.prayer.key)],
                                [_btn("🔙 نماز اول وقت", owner_id, "first")],
                            ]
                        ),
                    )

            elif action == "claim" and args:
                out = await ps.claim_prayer(session, user, args[0], now, timings)
                if out.result == ps.ClaimResult.SUCCESS:
                    page = (
                        tx.prayer_claim_success(out.prayer, out.noor_reward, out.noor_current),
                        _kb([[_btn("🔙 نماز اول وقت", owner_id, "first")]]),
                    )
                else:
                    if out.result == ps.ClaimResult.ALREADY_CLAIMED:
                        toast = tx.PRAYER_ALREADY_CLAIMED
                    elif out.result in (ps.ClaimResult.TOO_EARLY, ps.ClaimResult.TOO_LATE) and out.prayer:
                        state = (
                            pt.WindowState.BEFORE
                            if out.result == ps.ClaimResult.TOO_EARLY
                            else pt.WindowState.AFTER
                        )
                        toast = tx.prayer_locked_toast(out.prayer, out.adhan_at, state)
                        alert = True
                    else:
                        toast, alert = tx.PRAYER_UNAVAILABLE, True
                    page = await page_first(session, user, owner_id, now, timings)

            elif action == "claimed":
                toast = tx.PRAYER_ALREADY_CLAIMED

            elif action == "lessons":
                page = await page_lessons(user, owner_id)

            elif action == "soon":
                toast = tx.LESSON_COMING_SOON

            elif action == "lesson" and args and args[0].isdigit():
                lesson = ld.LESSON_BY_NUMBER.get(int(args[0]))
                if lesson is None or not lesson.available:
                    toast = tx.LESSON_COMING_SOON
                elif not ls.is_lesson_unlocked(user, lesson.number):
                    toast, alert = tx.LESSON_LEVEL_TOO_LOW, True
                else:
                    if ls.needs_listen(lesson.number) and (lesson.media or _audio_url_for(lesson.number)):
                        ls.start_listening(user, now, lesson.number)  # فایل همین الان نمایش داده می‌شود
                    page = page_lesson(user, owner_id, lesson, now)
                    audio_lesson = lesson if (lesson.media or _audio_url_for(lesson.number)) else None
                    media_lesson = lesson if lesson.media else None

            elif action == "heard" and args and args[0].isdigit():
                lesson = ld.LESSON_BY_NUMBER.get(int(args[0]))
                if lesson is None or not lesson.available:
                    toast = tx.LESSON_COMING_SOON
                else:
                    heard_result, wait = ls.confirm_heard(user, now, lesson.number)
                    if heard_result == ls.HeardResult.TOO_EARLY:
                        toast, alert = tx.heard_too_early_toast(wait), True
                    elif heard_result == ls.HeardResult.NOT_STARTED:
                        toast, alert = tx.HEARD_NOT_STARTED, True
                    page = page_lesson(user, owner_id, lesson, now)
                    audio_lesson = lesson if (lesson.media or _audio_url_for(lesson.number)) else None

            elif action == "exam" and args and args[0].isdigit():
                lesson_no = int(args[0])
                started = await ls.start_exam(session, user, lesson_no, now)
                if started.result == ls.ExamStartResult.OK:
                    exam_start = ("ok", started.exam)
                elif started.result == ls.ExamStartResult.ALREADY_PASSED:
                    exam_start = ("toast", tx.EXAM_ALREADY_PASSED)
                elif started.result == ls.ExamStartResult.NOT_HEARD:
                    exam_start = ("toast", tx.EXAM_NOT_HEARD)
                elif started.result == ls.ExamStartResult.LEVEL_TOO_LOW:
                    exam_start = ("toast", tx.LESSON_LEVEL_TOO_LOW)
                elif started.result == ls.ExamStartResult.COOLDOWN:
                    exam_start = ("toast", tx.exam_cooldown_toast(started.retry_after_seconds))
                else:
                    exam_start = ("toast", tx.EXAM_UNAVAILABLE)
                lesson = ld.LESSON_BY_NUMBER.get(lesson_no)
                if lesson is not None:
                    page = page_lesson(user, owner_id, lesson, now)
                    audio_lesson = lesson if (lesson.media or _audio_url_for(lesson.number)) else None

            if page is None:
                page = page_home(owner_id)
            text, kb = page

            # سؤال اول/جاری آزمون (برای ارسال بعد از commit)
            first_question = None
            if exam_start and exam_start[0] == "ok":
                exam = exam_start[1]
                current = ls.current_question(exam)
                if current is not None:
                    lesson = ld.LESSON_BY_NUMBER[exam.lesson_no]
                    first_question = (exam.id, current[0], current[1], lesson)

    # ----------------------- بعد از commit: ارسال پیام‌ها -----------------------
    if exam_start and exam_start[0] == "toast":
        toast, alert = exam_start[1], True

    if first_question is not None:
        exam_id, position, question, lesson = first_question
        sent = await _send_exam_question(callback, owner_id, exam_id, position, question, lesson)
        if sent:
            toast, alert = tx.EXAM_SENT_TO_PV, False
            if callback.message.chat.type == "private":
                toast = None  # سؤال همین‌جا آمد؛ توست اضافه لازم نیست
        else:
            await _edit_with_start_button(callback)
            await callback.answer(tx.EXAM_NEED_START_PV, show_alert=True)
            return

    await callback.answer(toast, show_alert=alert) if toast else await callback.answer()
    audio_url = _audio_url_for(audio_lesson.number) if audio_lesson is not None else None
    if audio_lesson is not None:
        logger.info("lesson %s audio preview url: %r", audio_lesson.number, audio_url)
    await _edit(callback, text, kb, audio_url=audio_url or None)

    if media_lesson is not None and not audio_url:
        # بدون لینک کانال: فایل جدا ارسال می‌شود (رفتار قبلی)
        await _send_lesson_media(callback.bot, callback.message.chat.id, media_lesson)


def _exam_keyboard(exam_id: int, position: int, question: ld.Question) -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                InlineKeyboardButton(
                    text=str(index),
                    callback_data=f"exq:{exam_id}:{position}:{index - 1}",
                )
                for index in range(1, len(question.options) + 1)
            ]
        ]
    )


async def _send_exam_question(callback, owner_id, exam_id, position, question, lesson) -> bool:
    """سؤال را در PV صاحب پنل می‌فرستد. False یعنی ربات اجازه‌ی پیام دادن در PV ندارد."""
    text = tx.exam_question(position, len(lesson.questions), question, lesson)
    try:
        await callback.bot.send_message(
            owner_id, text, reply_markup=_exam_keyboard(exam_id, position, question)
        )
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False
    except Exception:  # noqa: BLE001
        logger.exception("ارسال سؤال آزمون ناموفق بود")
        return False


async def _edit_with_start_button(callback: CallbackQuery) -> None:
    """وقتی کاربر ربات را در PV استارت نکرده: دکمه‌ی لینک مستقیم به PV ربات."""
    try:
        me = await callback.bot.get_me()
        markup = _kb([[InlineKeyboardButton(text=tx.EXAM_START_PV_BUTTON, url=f"https://t.me/{me.username}?start=exam")]])
        await callback.message.answer(tx.EXAM_NEED_START_PV, reply_markup=markup)
    except Exception:  # noqa: BLE001
        logger.debug("ارسال دکمه‌ی استارت ناموفق بود", exc_info=True)


# ---------------------------------------------------------------------------
# جواب سؤال‌های آزمون (PV)
# ---------------------------------------------------------------------------


@router.callback_query(lambda c: c.data and c.data.startswith("exq:"))
async def on_exam_answer(callback: CallbackQuery, event_update: Update) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 4 or not all(p.isdigit() for p in parts[1:]):
        return
    exam_id, position, option = int(parts[1]), int(parts[2]), int(parts[3])

    now = datetime.now(timezone.utc)
    next_question = None
    result_text: str | None = None

    async with async_session_factory() as session:
        async with session.begin():
            if not await try_claim_update(session, event_update.update_id):
                await callback.answer()
                return
            user = await get_or_create_user(
                session, callback.from_user.id, callback.from_user.username, callback.from_user.first_name
            )
            out = await ls.submit_answer(session, user, exam_id, position, option, now)

            if out.status == ls.AnswerStatus.NEXT:
                current = ls.current_question(out.exam)
                lesson = ld.LESSON_BY_NUMBER[out.exam.lesson_no]
                next_question = (out.exam.id, current[0], current[1], lesson)
            elif out.status == ls.AnswerStatus.FINISHED:
                lesson = ld.LESSON_BY_NUMBER[out.exam.lesson_no]
                by_id = {q.id: q for q in lesson.questions}
                result_text = tx.exam_result(out.grade, lesson, by_id, out.retry_after_seconds)

    if out.status == ls.AnswerStatus.STALE:
        await callback.answer(tx.EXAM_STALE)
        return

    await callback.answer()
    try:
        if next_question is not None:
            exam_id, position, question, lesson = next_question
            await callback.message.edit_text(
                tx.exam_question(position, len(lesson.questions), question, lesson),
                reply_markup=_exam_keyboard(exam_id, position, question),
            )
        elif result_text is not None:
            await callback.message.edit_text(result_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("edit آزمون ناموفق بود: %s", exc)
