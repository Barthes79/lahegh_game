-- Migration 0017: «شنیدم» در درس ۱ — بعد از ۱ دقیقه از باز کردن درس قابل کلیک است و بعدش دکمه‌ی آزمون می‌آید.
ALTER TABLE users ADD COLUMN lesson1_listen_started_at TEXT;
ALTER TABLE users ADD COLUMN lesson1_heard INTEGER NOT NULL DEFAULT 0;

-- کسی که آزمون درس ۱ را قبول شده، درس را شنیده است.
UPDATE users SET lesson1_heard = 1 WHERE lesson1_passed = 1;
