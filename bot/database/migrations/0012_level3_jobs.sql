-- Migration 0012: Level 3 — مشاغل، ابزار، مارکت (تومان) و انبار محصولات.
ALTER TABLE users ADD COLUMN job_key TEXT;
ALTER TABLE users ADD COLUMN job_selected_at TEXT;
ALTER TABLE users ADD COLUMN tool_level INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN toman INTEGER NOT NULL DEFAULT 0;

-- مواد اولیه‌ی خریداری‌شده از مارکت (بذر، علوفه، گیاه، جنس، پلاستیک) به‌ازای هر محصول
CREATE TABLE IF NOT EXISTS user_raw_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_key TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, product_key)
);

-- تولید فعال: هر کاربر در هر لحظه حداکثر یک تولید در جریان دارد
CREATE TABLE IF NOT EXISTS user_productions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    product_key TEXT NOT NULL,
    dhikr_done INTEGER NOT NULL DEFAULT 0,
    dhikr_required INTEGER NOT NULL,
    started_at TEXT NOT NULL
);

-- انبار محصولات تولیدشده، جدا شده بر اساس کیفیت (ستاره)
CREATE TABLE IF NOT EXISTS user_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_key TEXT NOT NULL,
    stars INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, product_key, stars)
);
