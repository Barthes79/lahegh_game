-- Migration 0003: Level 2 — حلقه ذکر
-- این فایل باید همیشه با bot/database/models.py هماهنگ بماند.
-- هرگز این فایل را بعد از انتشار ویرایش نکن؛ برای تغییرات بعدی 0004_xxx.sql بساز.

CREATE TABLE IF NOT EXISTS dhikr_circles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    milestone_paid_date TEXT
);

-- کاربر فقط عضو یک حلقه‌ی فعال می‌تواند باشد؛ این ستون منبع اصلی حقیقت است.
ALTER TABLE users ADD COLUMN active_circle_id INTEGER REFERENCES dhikr_circles(id);

CREATE TABLE IF NOT EXISTS dhikr_circle_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    circle_id INTEGER NOT NULL REFERENCES dhikr_circles(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    joined_at TEXT NOT NULL,
    left_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    left_reason TEXT,
    daily_count INTEGER NOT NULL DEFAULT 0,
    daily_date TEXT,
    daily_completed_at TEXT
);

-- برای پیدا کردن اعضای فعال یک حلقه و شمارش «۵ نفر زودتر تکمیل‌کننده»
CREATE INDEX IF NOT EXISTS idx_circle_members_circle_status ON dhikr_circle_members(circle_id, status);
CREATE INDEX IF NOT EXISTS idx_circle_members_user ON dhikr_circle_members(user_id);
