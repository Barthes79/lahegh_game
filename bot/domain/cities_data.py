"""
لیست شهرهای قابل انتخاب برای اوقات شرعی (دکمه‌ی «موقعیت مکانی» در بخش نماز).

نیازی به API جدید نیست: Aladhan اوقات را از روی مختصات (latitude/longitude) حساب می‌کند.
هر کاربر یک شهر انتخاب می‌کند و کلید آن (City.key) در users.prayer_city ذخیره می‌شود؛
کاربری که شهری انتخاب نکرده، از شهر پیش‌فرض تنظیمات سرور (PRAYER_* در .env) استفاده می‌کند.

برای اضافه کردن شهر: یک City جدید به CITIES اضافه کن (key انگلیسی، کوتاه و یکتا؛ حداکثر ~۲۰ حرف
چون داخل callback_data تلگرام می‌رود). مختصات را با دقت دو تا چهار رقم اعشار بگذار.
"""
from __future__ import annotations

from dataclasses import dataclass

CITIES_PER_PAGE = 8  # ۴ ردیف دو ستونه


@dataclass(frozen=True)
class City:
    key: str
    name: str  # نام فارسی برای نمایش
    latitude: float
    longitude: float
    timezone: str = "Asia/Tehran"


CITIES: tuple[City, ...] = (
    City("tehran", "تهران", 35.6892, 51.3890),
    City("mashhad", "مشهد", 36.2605, 59.6168),
    City("isfahan", "اصفهان", 32.6546, 51.6680),
    City("shiraz", "شیراز", 29.5918, 52.5837),
    City("tabriz", "تبریز", 38.0962, 46.2738),
    City("karaj", "کرج", 35.8400, 50.9391),
    City("qom", "قم", 34.6399, 50.8759),
    City("ahvaz", "اهواز", 31.3183, 48.6706),
    City("kermanshah", "کرمانشاه", 34.3277, 47.0778),
    City("urmia", "ارومیه", 37.5527, 45.0761),
    City("rasht", "رشت", 37.2808, 49.5832),
    City("zahedan", "زاهدان", 29.4963, 60.8629),
    City("kerman", "کرمان", 30.2839, 57.0834),
    City("hamadan", "همدان", 34.7992, 48.5146),
    City("yazd", "یزد", 31.8974, 54.3569),
    City("ardabil", "اردبیل", 38.2498, 48.2933),
    City("bandarabbas", "بندرعباس", 27.1865, 56.2808),
    City("arak", "اراک", 34.0954, 49.6892),
    City("zanjan", "زنجان", 36.6736, 48.4787),
    City("sanandaj", "سنندج", 35.3219, 46.9862),
    City("qazvin", "قزوین", 36.2797, 50.0049),
    City("khorramabad", "خرم‌آباد", 33.4878, 48.3558),
    City("gorgan", "گرگان", 36.8427, 54.4439),
    City("sari", "ساری", 36.5633, 53.0601),
    City("bojnord", "بجنورد", 37.4747, 57.3290),
    City("birjand", "بیرجند", 32.8649, 59.2262),
    City("bushehr", "بوشهر", 28.9234, 50.8203),
    City("ilam", "ایلام", 33.6374, 46.4227),
    City("shahrekord", "شهرکرد", 32.3256, 50.8644),
    City("yasuj", "یاسوج", 30.6682, 51.5880),
    City("semnan", "سمنان", 35.5769, 53.3920),
    City("neyshabur", "نیشابور", 36.2133, 58.7958),
    City("kashan", "کاشان", 33.9850, 51.4100),
    City("kish", "کیش", 26.5579, 53.9807),
)
CITY_BY_KEY: dict[str, City] = {city.key: city for city in CITIES}


def get_city(key: str | None) -> City | None:
    return CITY_BY_KEY.get(key) if key else None


def page_count() -> int:
    return (len(CITIES) + CITIES_PER_PAGE - 1) // CITIES_PER_PAGE


def clamp_page(page: int) -> int:
    return max(0, min(page, page_count() - 1))


def cities_on_page(page: int) -> tuple[City, ...]:
    page = clamp_page(page)
    start = page * CITIES_PER_PAGE
    return CITIES[start : start + CITIES_PER_PAGE]
