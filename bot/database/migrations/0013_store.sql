-- Migration 0013: فروشگاه — آگهی‌های کاربران و انتظار ورود قیمت.

-- آگهی فروش کاربر. تعداد آگهی از انبار فروشنده کم شده (escrow) و با لغو/اتمام تعیین تکلیف می‌شود.
CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL REFERENCES users(id),
    product_key TEXT NOT NULL,
    stars INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_market_listings_product ON market_listings(product_key, unit_price);
CREATE INDEX IF NOT EXISTS ix_market_listings_seller ON market_listings(seller_id);

-- کاربر بعد از انتخاب کالا برای آگهی، باید روی پیام پنل «ریپلای» کند و قیمت را بنویسد.
CREATE TABLE IF NOT EXISTS market_price_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    product_key TEXT NOT NULL,
    stars INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
