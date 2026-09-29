-- Migration 0014: بانک — شماره کارت، زندان، و قرض‌الحسنه.
-- توجه: موجودی بانکی کاربر همان users.toman است؛ ستون جدیدی برای «موجودی» ساخته نشده
-- چون طبق طراحی، پول محصولات و همه‌ی تراکنش‌ها مستقیماً در همان‌جا نگه‌داری می‌شود.

ALTER TABLE users ADD COLUMN card_number TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_card_number ON users(card_number);

-- کاربر تا این زمان در «زندان» است و نمی‌تواند صلوات/ذکر ثبت کند (پیامد ندادن بدهی).
ALTER TABLE users ADD COLUMN jail_until TEXT;

-- درخواست کاربر برای دریافت پول از فردی دیگر با شماره کارت (سازگار با ریپلای دوباره).
CREATE TABLE IF NOT EXISTS bank_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    kind TEXT NOT NULL,  -- 'transfer' | 'loan'
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id INTEGER NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    repay_amount INTEGER NOT NULL,
    lender_noor_reward INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | funded | repaid
    lender_id INTEGER REFERENCES users(id),
    requested_at TEXT NOT NULL,
    funded_at TEXT,
    due_at TEXT,
    repaid_at TEXT,
    last_penalty_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_loan_requests_status ON loan_requests(status);
CREATE INDEX IF NOT EXISTS ix_loan_requests_borrower ON loan_requests(borrower_id);
