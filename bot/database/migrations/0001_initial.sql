-- Migration 0001: schema اولیه بازی «لاحق» Level 1
-- این فایل باید همیشه با bot/database/models.py هماهنگ بماند.
-- برای تغییرات آینده: فایل migration جدید با شماره بعدی اضافه کن (مثلاً 0002_xxx.sql)،
-- هرگز این فایل را بعد از انتشار ویرایش نکن.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    created_at TEXT NOT NULL,

    game_started INTEGER NOT NULL DEFAULT 0,
    game_started_at TEXT,
    active_chat_id INTEGER,

    level INTEGER NOT NULL DEFAULT 0,
    level_progress INTEGER NOT NULL DEFAULT 0,

    noor_current INTEGER NOT NULL DEFAULT 0,
    noor_total_earned INTEGER NOT NULL DEFAULT 0,

    salawat_count INTEGER NOT NULL DEFAULT 0,
    dhikr_count INTEGER NOT NULL DEFAULT 0,
    total_activities INTEGER NOT NULL DEFAULT 0,

    last_activity_at TEXT,
    last_salawat_at TEXT,
    last_dhikr_at TEXT,
    last_dhikr_cooldown_seconds INTEGER,

    reaction_explained INTEGER NOT NULL DEFAULT 0,

    bank_azkar_unlocked INTEGER NOT NULL DEFAULT 0,
    nameh_amal_unlocked INTEGER NOT NULL DEFAULT 0,
    tasbih_unlocked INTEGER NOT NULL DEFAULT 0,
    tasbih_level INTEGER NOT NULL DEFAULT 0,

    chest_count INTEGER NOT NULL DEFAULT 0,
    first_chest_explained INTEGER NOT NULL DEFAULT 0,
    last_chest_created_at TEXT,

    last_reminder_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

CREATE TABLE IF NOT EXISTS dhikr_unlocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    dhikr_key TEXT NOT NULL,
    unlocked_at TEXT NOT NULL,
    UNIQUE(user_id, dhikr_key)
);

CREATE TABLE IF NOT EXISTS chests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    chat_id INTEGER NOT NULL,
    message_id INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    opened INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT,
    reward_noor INTEGER
);

CREATE INDEX IF NOT EXISTS idx_chests_user_id ON chests(user_id);

-- برای جلوگیری از پردازش دوباره‌ی یک update تلگرام (بخش ۲۰ سند: anti-exploit/atomicity)
CREATE TABLE IF NOT EXISTS processed_updates (
    update_id INTEGER PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
