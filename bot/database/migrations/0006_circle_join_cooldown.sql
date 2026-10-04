-- Migration 0006: cooldown خروج -> پیوستن دوباره به حلقه
ALTER TABLE users ADD COLUMN circle_join_cooldown_until TEXT;
