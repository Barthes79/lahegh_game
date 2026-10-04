"""
ابزار ادمین: گرفتن file_id معتبر برای همین ربات.

file_id تلگرام به رباتی که فایل را دریافت کرده قفل است؛ file_id گرفته‌شده از ربات دیگر با خطای
«wrong file identifier» رد می‌شود. راه درست: ادمین فایل را در PV همین ربات می‌فرستد و ربات
file_id همان فایل را برمی‌گرداند. بعد آن را در bot/domain/lessons_data.py می‌گذارید.

شرط: آیدی عددی ادمین در متغیر ADMIN_IDS (جدا شده با کاما) باشد. «/id» آیدی عددی خودتان را نشان می‌دهد.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings

router = Router(name="admin_tools")

# kind در LessonMedia برای هر نوع فایل تلگرام
_LESSON_KIND = {"audio": "audio", "video": "video", "document": "pdf"}


def extract_file(message) -> tuple[str, str] | None:
    """(نوع فایل، file_id) یا None اگر پیام فایلی ندارد."""
    for attr in ("audio", "voice", "video", "video_note", "animation", "document"):
        obj = getattr(message, attr, None)
        if obj is not None:
            return attr, obj.file_id
    photos = getattr(message, "photo", None)
    if photos:
        return "photo", photos[-1].file_id  # بزرگ‌ترین اندازه
    return None


def is_admin_media(message) -> bool:
    chat = getattr(message, "chat", None)
    user = getattr(message, "from_user", None)
    return (
        chat is not None
        and chat.type == "private"
        and user is not None
        and user.id in settings.admin_ids
        and extract_file(message) is not None
    )


def build_reply(kind: str, file_id: str) -> str:
    lines = [f"🆔 <b>file_id</b> ({kind}) برای همین ربات:", "", f"<code>{file_id}</code>", ""]
    lesson_kind = _LESSON_KIND.get(kind)
    if lesson_kind:
        lines.append(f"برای درس: <code>LessonMedia(\"{lesson_kind}\", file_id=\"...\")</code>")
        lines.append("درس ۱ → ثابت <code>LESSON_1_AUDIO_FILE_ID</code> در lessons_data.py")
    elif kind == "voice":
        lines.append("⚠️ این یک ویس است. برای درس، فایل را به‌صورت Audio/Music بفرست.")
    return "\n".join(lines)


@router.message(is_admin_media)
async def on_admin_media(message: Message) -> None:
    kind, file_id = extract_file(message)  # type: ignore[misc]
    await message.reply(build_reply(kind, file_id))


@router.message(Command("id"))
async def on_my_id(message: Message) -> None:
    """آیدی عددی خود کاربر (برای پر کردن ADMIN_IDS)."""
    if message.from_user is None:
        return
    await message.reply(f"آیدی عددی تو: <code>{message.from_user.id}</code>")
