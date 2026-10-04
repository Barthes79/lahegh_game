"""
راه‌اندازی دیتابیس: engine غیرهمزمان، session factory و اجرای migrationها.

برای اطمینان از atomicity (بخش ۲۰ سند)، هر تراکنش نوشتاری به‌صورت
`BEGIN IMMEDIATE` روی SQLite اجرا می‌شود تا نوشتن‌های همزمان به‌جای race condition،
به‌ترتیب صف بشوند (WAL mode هم‌زمان امکان خواندن هم‌زمان را حفظ می‌کند).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_engine = create_async_engine(f"sqlite+aiosqlite:///{settings.database_path}", echo=False)


@event.listens_for(_engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    # اجازه بده خودمان کنترل BEGIN را دست بگیریم (طبق توصیه رسمی SQLAlchemy برای pysqlite/aiosqlite)
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@event.listens_for(_engine.sync_engine, "begin")
def _do_begin(conn) -> None:  # noqa: ANN001
    # BEGIN IMMEDIATE به‌جای BEGIN معمولی: قفل نوشتن بلافاصله گرفته می‌شود
    # و race condition بین تراکنش‌های هم‌زمان (double click, retry و ...) از بین می‌رود.
    conn.exec_driver_sql("BEGIN IMMEDIATE")


async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


async def run_migrations() -> None:
    """اجرای migrationهای اعمال‌نشده، به ترتیب شماره فایل."""
    async with aiosqlite.connect(settings.database_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        await conn.commit()

        cursor = await conn.execute("SELECT version FROM schema_migrations")
        applied = {row[0] for row in await cursor.fetchall()}

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for path in files:
            try:
                version = int(path.name.split("_", 1)[0])
            except ValueError:
                logger.warning("نام فایل migration نامعتبر است و رد شد: %s", path.name)
                continue
            if version in applied:
                continue
            logger.info("در حال اجرای migration %s ...", path.name)
            sql = path.read_text(encoding="utf-8")
            await conn.executescript(sql)
            await conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            await conn.commit()
            logger.info("migration %s اعمال شد.", path.name)


def get_engine():
    return _engine
