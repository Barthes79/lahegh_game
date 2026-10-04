-- Migration 0016: شهر انتخابی کاربر برای اوقات شرعی (دکمه‌ی «موقعیت مکانی» در بخش نماز).
-- NULL یعنی کاربر شهری انتخاب نکرده و شهر پیش‌فرض تنظیمات سرور (PRAYER_* در .env) استفاده می‌شود.
ALTER TABLE users ADD COLUMN prayer_city TEXT;
