from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database.engine import run_migrations
from bot.handlers import (
    bank_panel,
    callbacks,
    commands,
    dhikr_circle,
    dua_queue,
    group_messages,
    bank_panel,
    job_panel,
    store_panel,
    tasbih_panel,
)
from bot.jobs.scheduler import reminder_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است. فایل .env را بر اساس .env.example بساز.")

    await run_migrations()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # ترتیب مهم است: دستورات ثابت بازی قبل از catch-all پیام‌های بازی ثبت شوند
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(tasbih_panel.router)
    dp.include_router(dua_queue.router)
    dp.include_router(dhikr_circle.router)
    dp.include_router(job_panel.router)
    dp.include_router(store_panel.router)
    dp.include_router(bank_panel.router)
    dp.include_router(group_messages.router)

    reminder_task = asyncio.create_task(reminder_loop(bot))

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
