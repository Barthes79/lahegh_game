-- Migration 0018: آزمون درس ۲ — قبولی شرط رفتن از سطح ۲ به سطح ۳ است.
ALTER TABLE users ADD COLUMN lesson2_passed INTEGER NOT NULL DEFAULT 0;

-- کسی که الان سطح ۳ یا بالاتر است، قبلاً از سطح ۲ رد شده؛ مجبور به آزمون نیست.
UPDATE users SET lesson2_passed = 1 WHERE level >= 3;
