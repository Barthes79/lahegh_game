-- Migration 0004: قوانین نهایی حلقه ذکر
-- نام حلقه، قفل پاداش گروهی پس از خروج عضو، و پاداش شخصی روزانه.

ALTER TABLE dhikr_circles ADD COLUMN name TEXT NOT NULL DEFAULT 'حلقه ذکر';
ALTER TABLE dhikr_circles ADD COLUMN group_bonus_blocked_date TEXT;
ALTER TABLE users ADD COLUMN circle_personal_reward_date TEXT;

-- یکتایی نام حلقه برای حلقه‌های جدید در سرویس کنترل می‌شود تا داده‌های قدیمی نشکنند.
