-- Migration 0009: پنجره‌ی ۲۴ ساعته‌ی حلقه و سهم سراسری هر کاربر.
ALTER TABLE users ADD COLUMN circle_daily_dhikr_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN circle_daily_dhikr_started_at TEXT;
ALTER TABLE users DROP COLUMN circle_join_cooldown_until;

ALTER TABLE dhikr_circles ADD COLUMN started_at TEXT;
ALTER TABLE dhikr_circles ADD COLUMN expires_at TEXT;

ALTER TABLE dhikr_circle_members ADD COLUMN panel_chat_id INTEGER;
ALTER TABLE dhikr_circle_members ADD COLUMN panel_message_id INTEGER;
