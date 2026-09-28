-- Migration 0007: ذکر تصادفی نمایشی وقتی کاربر «حلقه ذکر» می‌نویسد.
-- برای هر کاربر یک ذکر (از میان ۵ ذکر ویژه) به‌صورت تصادفی انتخاب و ۲۴ ساعت ثابت نگه داشته می‌شود.
ALTER TABLE users ADD COLUMN circle_display_dhikr_key TEXT;
ALTER TABLE users ADD COLUMN circle_display_dhikr_assigned_at TEXT;
