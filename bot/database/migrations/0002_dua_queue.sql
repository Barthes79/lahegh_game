-- Migration 0002: Level 2 — صف دعا (التماس دعا)
-- این فایل باید همیشه با bot/database/models.py هماهنگ بماند.
-- هرگز این فایل را بعد از انتشار ویرایش نکن؛ برای تغییرات بعدی 0003_xxx.sql بساز.

-- سهمیه‌ی روزانه‌ی ذکر رایگان (صلوات حساب نمی‌شود)؛ شرط باز شدن صف دعا برای همان روز.
-- مبنای روز Asia/Tehran است (bot/domain/dua_queue.py: tehran_date_str).
ALTER TABLE users ADD COLUMN daily_free_dhikr_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN daily_free_dhikr_date TEXT;

CREATE TABLE IF NOT EXISTS dua_queues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    chat_id INTEGER NOT NULL,
    message_id INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    answers_count INTEGER NOT NULL DEFAULT 0,
    closed INTEGER NOT NULL DEFAULT 0,
    closed_reason TEXT
);

-- برای بررسی سریع «آیا این کاربر در ۲۴ ساعت گذشته صف ساخته؟»
CREATE INDEX IF NOT EXISTS idx_dua_queues_owner_created ON dua_queues(owner_user_id, created_at);

-- برای شمارش «اعضای فعال گروه» و پیدا کردن صف‌های یک چت
CREATE INDEX IF NOT EXISTS idx_dua_queues_chat ON dua_queues(chat_id);

CREATE TABLE IF NOT EXISTS dua_queue_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id INTEGER NOT NULL REFERENCES dua_queues(id),
    responder_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(queue_id, responder_user_id)
);

CREATE INDEX IF NOT EXISTS idx_dua_queue_answers_responder ON dua_queue_answers(responder_user_id);
