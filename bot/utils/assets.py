"""مسیر فایل‌های عکس ثابت پنل‌ها (بانک اذکار، تسبیح)."""
from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

BANK_AZKAR_PHOTO_PATH = ASSETS_DIR / "bank_azkar_panel.png"
TASBIH_PHOTO_PATH = ASSETS_DIR / "tasbih_panel.png"
