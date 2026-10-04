# لاحق — Level 1

ربات تلگرامی بازی مذهبی «لاحق» (صلوات و ذکر برای دریافت نور). پیاده‌سازی کامل Level 1
طبق سند مشخصات اولیه + اصلاحات نهایی تأییدشده (نسخه‌ی فعلی).

نکات کلیدی نسخه‌ی فعلی:
- شروع بازی فقط با اولین صلوات معتبر **در گروه** است؛ `/start` نقشی در شروع بازی ندارد.
- فعالیت (صلوات/ذکر) فقط در گروه ثبت می‌شود؛ پیام در PV هرگز فعالیت محسوب نمی‌شود.
- ۶۷٪ فعالیت‌ها: فقط reaction 🙏 در گروه + نتیجه بلافاصله در PV کاربر.
- ۳۳٪ فعالیت‌ها: پیام کامل در گروه، بدون پیام PV.
- صندوقچه: شانس ثابت ۲٪، مهلت باز کردن ۱ ساعت، cooldown پیدا شدن ۲۴ ساعت (مستقل از هم).

## نصب

```bash
python -m venv venv
source venv/bin/activate   # ویندوز: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# سپس BOT_TOKEN را داخل .env از BotFather بگذار
```

## اجرا

```bash
python run.py
```

با اجرا، migrationهای دیتابیس (`bot/database/migrations/*.sql`) به‌صورت خودکار روی فایل
SQLite مشخص‌شده در `DATABASE_PATH` اعمال می‌شوند و سپس ربات با polling شروع به کار می‌کند.

## تنظیمات (`.env`)

| متغیر | توضیح | پیش‌فرض |
|---|---|---|
| `BOT_TOKEN` | توکن ربات از BotFather | - (الزامی) |
| `DATABASE_PATH` | مسیر فایل SQLite | `laahiq.db` |
| `ADMIN_IDS` | آیدی‌های ادمین (برای آینده) | خالی |
| `REMINDER_INACTIVITY_HOURS` | بعد از چند ساعت بی‌فعالیتی یادآوری بفرست | `12` |
| `REMINDER_MIN_GAP_HOURS` | حداقل فاصله بین دو یادآوری متوالی برای یک کاربر | `24` |
| `REMINDER_CHECK_INTERVAL_MINUTES` | هر چند دقیقه سیستم یادآوری چک شود | `30` |

## تست

```bash
python tests/test_pipeline.py
```

این اسکریپت یک دیتابیس موقت در `/tmp` می‌سازد و کل پایپ‌لاین بازی را (شروع، cooldownها،
normalization، پیام نامعتبر، milestoneها، اقتصاد نور، تسبیح، و concurrency واقعی) تست می‌کند.

## ساختار پروژه

```
bot/
  config.py              تنظیمات مرکزی (از .env)
  database/
    models.py             مدل‌های SQLAlchemy
    engine.py              engine + session factory + اجرای migration
    migrations/*.sql       migrationهای SQL (منبع حقیقت schema)
  domain/                  منطق خالص بازی (بدون وابستگی به تلگرام/دیتابیس)
    normalization.py, salawat_data.py, dhikr_data.py, validator.py,
    cooldown.py, tasbih_data.py, chest.py, milestones.py
  services/                orchestration + دسترسی به دیتابیس
    activity_service.py    پایپ‌لاین اصلی پردازش فعالیت (بخش ۱۰ سند)
    unlock_service.py, tasbih_service.py, chest_service.py,
    reminder_service.py, idempotency.py, user_service.py
  handlers/                لایه‌ی تلگرام (aiogram)
    group_messages.py, commands.py, callbacks.py
  keyboards/inline.py       دکمه‌های inline
  texts/messages.py         تمام متن‌های نمایشی
  jobs/scheduler.py         تسک پس‌زمینه‌ی یادآوری
  main.py                   نقطه‌ی راه‌اندازی dispatcher
tests/test_pipeline.py      تست‌های end-to-end
run.py                      نقطه‌ی ورود اجرا
```

## افزودن صلوات/ذکر جدید در آینده

- صلوات جدید: یک رشته به `SALAWAT_VARIANTS` در `bot/domain/salawat_data.py` اضافه کن.
- ذکر جدید: یک `DhikrDefinition` به `DHIKR_LIST` در `bot/domain/dhikr_data.py` اضافه کن.

هیچ تغییر دیگری در بقیه‌ی سیستم لازم نیست (بانک اذکار، پایپ‌لاین فعالیت، و unlock به‌صورت
خودکار آن را پشتیبانی می‌کنند).

## افزودن migration جدید در آینده

فایل جدید با شماره‌ی بعدی در `bot/database/migrations/` بساز (مثلاً `0002_xxx.sql`)، شامل
`ALTER TABLE` یا `CREATE TABLE` لازم. هرگز فایل‌های قبلی را ویرایش نکن. مدل‌های
`bot/database/models.py` را هم هم‌زمان به‌روزرسانی کن. با اجرای بعدی ربات، migration جدید
خودکار اعمال می‌شود و داده‌های قبلی دست‌نخورده می‌مانند.

## استقرار روی Railway

- کل پروژه (شامل `run.py` و `requirements.txt` در ریشه) باید آپلود شود، نه فقط پوشه‌ی `bot/`.
- دستور شروع در `railway.json` تنظیم شده است: `python run.py`.
- در Variables سرویس حتماً `BOT_TOKEN` را بگذارید.
- **دیتابیس:** فایل‌سیستم Railway موقتی است و با هر دیپلوی پاک می‌شود. یک **Volume** به سرویس وصل کنید
  (مثلاً روی `/data`) و `DATABASE_PATH=/data/laahiq.db` را در Variables بگذارید؛ وگرنه با هر دیپلوی همه‌ی
  اطلاعات کاربران صفر می‌شود.
- اوقات شرعی از `api.aladhan.com` گرفته می‌شود؛ متغیرهای `PRAYER_*` در `.env.example` توضیح داده شده‌اند.
