-- Migration 0011: التماس دعا — پیام‌های اضافه‌ی مرتبط با یک پنل
-- وقتی صاحب پنلِ باز دوباره «التماس دعا» می‌زند، وضعیت پنل (همراه ذکر) در یک پیام جدید
-- نمایش داده می‌شود. ریپلای روی آن پیام هم باید مثل ریپلای روی پنل اصلی پاسخ حساب شود.
CREATE TABLE IF NOT EXISTS dua_queue_extra_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id INTEGER NOT NULL REFERENCES dua_queues(id),
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    UNIQUE(chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_dua_queue_extra_chat_message ON dua_queue_extra_messages(chat_id, message_id);
