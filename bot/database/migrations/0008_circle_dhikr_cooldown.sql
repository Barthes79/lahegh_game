-- Migration 0008: کولداون مستقل برای ذکرهای ویژه‌ی «حلقه ذکر» (جدا از کولداون ذکر عادی).
ALTER TABLE users ADD COLUMN last_circle_dhikr_at TEXT;
