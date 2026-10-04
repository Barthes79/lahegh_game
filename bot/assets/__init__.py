"""مسیر تصویرهای ثابت بالای پنل‌ها (بانک اذکار / تسبیح)."""
from __future__ import annotations

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent

BANK_AZKAR_PANEL_IMAGE = _ASSETS_DIR / "bank_azkar_panel.png"
TASBIH_PANEL_IMAGE = _ASSETS_DIR / "tasbih_panel.png"
