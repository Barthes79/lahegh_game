-- Migration 0019: «شنیدم» در درس ۲ (مثل درس ۱): ۱ دقیقه بعد از باز کردن درس قابل کلیک است.
ALTER TABLE users ADD COLUMN lesson2_listen_started_at TEXT;
ALTER TABLE users ADD COLUMN lesson2_heard INTEGER NOT NULL DEFAULT 0;

-- کسی که آزمون درس ۲ را قبول شده (یا از قبل سطح ۳+ است)، درس را شنیده است.
UPDATE users SET lesson2_heard = 1 WHERE lesson2_passed = 1;
