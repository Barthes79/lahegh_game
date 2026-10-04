-- Migration 0015: «مسیر انتظار» (سطح ۱) — نماز اول وقت، دروس و آزمون.
-- جایگزین بانک اذکار شد؛ ستون bank_azkar_unlocked و جدول dhikr_unlocks عمداً دست‌نخورده می‌مانند.

-- آیا کاربر آزمون درس ۱ را قبول شده؟ (شرط رفتن از سطح ۱ به سطح ۲)
ALTER TABLE users ADD COLUMN lesson1_passed INTEGER NOT NULL DEFAULT 0;
-- زمان آخرین مردودی آزمون (برای انتظار ۱۵ دقیقه‌ای قبل از آزمون بعدی)
ALTER TABLE users ADD COLUMN exam_last_failed_at TEXT;

-- کاربرانی که از قبل در سطح ۲ یا بالاترند، از سطح ۱ گذشته‌اند.
UPDATE users SET lesson1_passed = 1 WHERE level >= 2;

-- ثبت «نماز اول وقت خواندم»: برای هر کاربر، هر نماز، هر روز فقط یک بار.
CREATE TABLE IF NOT EXISTS prayer_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    prayer_key TEXT NOT NULL,          -- subh | zuhrayn | maghribayn
    day TEXT NOT NULL,                 -- YYYY-MM-DD به وقت شهر تنظیم‌شده
    claimed_at TEXT NOT NULL,
    noor_reward INTEGER NOT NULL,
    UNIQUE(user_id, prayer_key, day)
);
CREATE INDEX IF NOT EXISTS ix_prayer_claims_user ON prayer_claims(user_id);

-- یک دور آزمون. question_order و answers رشته‌ی JSON هستند.
-- status: active | finished. هر کاربر حداکثر یک دور active دارد (ادامه‌ی آزمون نیمه‌کاره).
CREATE TABLE IF NOT EXISTS exam_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    lesson_no INTEGER NOT NULL,
    question_order TEXT NOT NULL,
    answers TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    score INTEGER,
    passed INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_exam_sessions_user ON exam_sessions(user_id, status);
