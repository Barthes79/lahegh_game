-- Migration 0010: التماس دعا — ذکر تصادفی هر پنل
-- کلید ذکری (از DUA_QUEUE_DHIKR_LIST در bot/domain/dhikr_data.py) که هنگام ساخت پنل
-- به‌صورت تصادفی انتخاب شده و پاسخ‌دهنده‌ها باید متنش را روی پیام پنل ریپلای کنند.
-- پنل‌های قدیمی (ساخته‌شده با مکانیزم دکمه) NULL می‌مانند و دیگر قابل پاسخ نیستند.
ALTER TABLE dua_queues ADD COLUMN dhikr_key TEXT;

-- برای پیدا کردن سریع پنل از روی پیامِ ریپلای‌شده
CREATE INDEX IF NOT EXISTS idx_dua_queues_chat_message ON dua_queues(chat_id, message_id);
