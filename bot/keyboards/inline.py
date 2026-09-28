"""
ساخت keyboardهای inline. callback_data کوتاه و ساختاریافته است تا هم در محدودیت ۶۴بایتی
تلگرام بگنجد و هم به‌سادگی در callback handler قابل تفسیر باشد.

فرمت‌های callback_data:
  dhikr_unlock_ask:<key>       -> نمایش تأییدیه unlock
  dhikr_unlock_confirm:<key>   -> اجرای unlock
  dhikr_unlock_cancel          -> انصراف
  chest_open:<chest_id>        -> باز کردن صندوقچه

  Level 2 — صف دعا:
  (dua_ans:<queue_id> منسوخ شد: التماس دعا اکنون با ریپلای روی پنل پاسخ داده می‌شود)

  پنل تسبیح (owner-scoped، مثل پنل بانک اذکار):
  tsb:main:<owner_id>            -> بازگشت به صفحه‌ی اصلی پنل تسبیح
  tsb:upgrade_ask:<owner_id>     -> نمایش تأییدیه ارتقا
  tsb:upgrade_confirm:<owner_id> -> اجرای ارتقا
  tsb:upgrade_cancel:<owner_id>  -> انصراف و بازگشت به صفحه‌ی اصلی
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.domain.dhikr_data import DhikrDefinition
from bot.texts import messages as texts

# ---------------------------------------------------------------------------
# پنل بانک اذکار (اصلاحات نهایی): callback_data شامل owner_id است تا در هندلر بتوان
# تشخیص داد کلیک از طرف صاحب پنل است یا نه.
#   bnk:main:<owner_id>              -> بازگشت به صفحه‌ی اصلی پنل
#   bnk:view:<owner_id>:<key>        -> نمایش صفحه‌ی جزئیات یک ذکر
#   bnk:buy:<owner_id>:<key>         -> تایید خرید همان ذکر
# ---------------------------------------------------------------------------


def bank_azkar_main_keyboard(
    owner_id: int, dhikr_list: list[DhikrDefinition], unlocked_map: dict[str, bool]
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=texts.bank_azkar_entry_button_label(dhikr, unlocked_map.get(dhikr.key, False)),
                callback_data=f"bnk:view:{owner_id}:{dhikr.key}",
            )
        ]
        for dhikr in dhikr_list
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bank_azkar_detail_keyboard(owner_id: int, dhikr_key: str, unlocked: bool) -> InlineKeyboardMarkup:
    back_row = [
        InlineKeyboardButton(text=texts.BANK_AZKAR_BACK_BUTTON_LABEL, callback_data=f"bnk:main:{owner_id}")
    ]
    if unlocked:
        return InlineKeyboardMarkup(inline_keyboard=[back_row])
    buy_row = [
        InlineKeyboardButton(
            text=texts.BANK_AZKAR_BUY_BUTTON_LABEL, callback_data=f"bnk:buy:{owner_id}:{dhikr_key}"
        )
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buy_row, back_row])


def bank_azkar_back_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BANK_AZKAR_BACK_BUTTON_LABEL, callback_data=f"bnk:main:{owner_id}"
                )
            ]
        ]
    )


def dhikr_unlock_button(dhikr: DhikrDefinition) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.UNLOCK_BUTTON_LABEL,
                    callback_data=f"dhikr_unlock_ask:{dhikr.key}",
                )
            ]
        ]
    )


def confirm_cancel_keyboard(confirm_data: str, cancel_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.CONFIRM_YES, callback_data=confirm_data),
                InlineKeyboardButton(text=texts.CONFIRM_NO, callback_data=cancel_data),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# پنل تسبیح: مثل پنل بانک اذکار، owner-scoped و تک‌پیامی (عکس + کپشن).
#   tsb:main:<owner_id>            -> صفحه‌ی اصلی
#   tsb:upgrade_ask:<owner_id>     -> تأییدیه‌ی ارتقا
#   tsb:upgrade_confirm:<owner_id> -> اجرای ارتقا
#   tsb:upgrade_cancel:<owner_id>  -> انصراف
# ---------------------------------------------------------------------------


def tasbih_panel_main_keyboard(owner_id: int, tasbih_level: int) -> InlineKeyboardMarkup:
    if tasbih_level >= 12:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.TASBIH_UPGRADE_BUTTON_LABEL, callback_data=f"tsb:upgrade_ask:{owner_id}"
                )
            ]
        ]
    )


def tasbih_panel_confirm_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.CONFIRM_YES, callback_data=f"tsb:upgrade_confirm:{owner_id}"
                ),
                InlineKeyboardButton(
                    text=texts.CONFIRM_NO, callback_data=f"tsb:upgrade_cancel:{owner_id}"
                ),
            ]
        ]
    )


def tasbih_panel_back_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.TASBIH_BACK_BUTTON_LABEL, callback_data=f"tsb:main:{owner_id}"
                )
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Level 2 — حلقه ذکر: owner-scoped، مثل پنل بانک اذکار/تسبیح
#   crc:main:<owner_id>                      -> صفحه‌ی اصلی
#   crc:create:<owner_id>                    -> ساخت حلقه (اگر عضو هیچ حلقه‌ای نیست)
#   crc:status:<owner_id>                    -> وضعیت حلقه (سهم امروز + milestone)
#   crc:members:<owner_id>                   -> فهرست اعضا
#   crc:invite:<owner_id>                    -> نمایش لینک دعوت
#   crc:leave_ask:<owner_id>                 -> تأییدیه‌ی خروج
#   crc:leave_confirm:<owner_id>             -> اجرای خروج
#   crc:leave_cancel:<owner_id>               -> انصراف، بازگشت به صفحه‌ی اصلی
#   crc:manage:<owner_id>                    -> فهرست اعضا برای حذف (فقط سازنده)
#   crc:remove_ask:<owner_id>:<target_id>    -> تأییدیه‌ی حذف عضو
#   crc:remove_confirm:<owner_id>:<target_id> -> اجرای حذف
#   crc:remove_cancel:<owner_id>              -> انصراف، بازگشت به مدیریت اعضا
# ---------------------------------------------------------------------------


def circle_no_circle_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.CIRCLE_CREATE_BUTTON_LABEL, callback_data=f"crc:create:{owner_id}"
                )
            ]
        ]
    )


def circle_main_keyboard(
    owner_id: int, is_creator: bool = False, can_claim_reward: bool = False
) -> InlineKeyboardMarkup:
    rows = []
    if can_claim_reward:
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.CIRCLE_CLAIM_REWARD_BUTTON_LABEL,
                    callback_data=f"crc:claim_reward:{owner_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.CIRCLE_LEAVE_BUTTON_LABEL, callback_data=f"crc:leave_ask:{owner_id}"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def circle_invite_confirmation_keyboard(target_id: int, circle_id: int, inviter_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.CIRCLE_INVITE_ACCEPT_BUTTON_LABEL,
                    callback_data=f"cinvite:accept:{target_id}:{circle_id}:{inviter_id}",
                ),
                InlineKeyboardButton(
                    text=texts.CIRCLE_INVITE_CANCEL_BUTTON_LABEL,
                    callback_data=f"cinvite:cancel:{target_id}:{circle_id}:{inviter_id}",
                ),
            ]
        ]
    )


def circle_back_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    # عمداً بدون دکمه؛ کاربر از پنل‌های فرعی با ارسال دوباره «حلقه ذکر» به صفحه اصلی برمی‌گردد.
    return InlineKeyboardMarkup(inline_keyboard=[])


def circle_leave_confirm_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.CONFIRM_YES, callback_data=f"crc:leave_confirm:{owner_id}"),
                InlineKeyboardButton(text=texts.CONFIRM_NO, callback_data=f"crc:leave_cancel:{owner_id}"),
            ]
        ]
    )


def circle_manage_keyboard(owner_id: int, members: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """members: لیست (target_user_id, نمایش‌نام) به‌جز خودِ سازنده."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"❌ {label}", callback_data=f"crc:remove_ask:{owner_id}:{target_id}"
            )
        ]
        for target_id, label in members
    ]
    rows.append(
        [InlineKeyboardButton(text=texts.CIRCLE_BACK_BUTTON_LABEL, callback_data=f"crc:main:{owner_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def circle_remove_confirm_keyboard(owner_id: int, target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.CONFIRM_YES, callback_data=f"crc:remove_confirm:{owner_id}:{target_id}"
                ),
                InlineKeyboardButton(text=texts.CONFIRM_NO, callback_data=f"crc:remove_cancel:{owner_id}"),
            ]
        ]
    )


def chest_open_button(chest_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.CHEST_OPEN_BUTTON_LABEL, callback_data=f"chest_open:{chest_id}"
                )
            ]
        ]
    )
def circle_manage_keyboard(owner_id: int, members: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """members: لیست (target_user_id, نمایش‌نام) به‌جز خودِ سازنده."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"❌ {label}", callback_data=f"crc:remove_ask:{owner_id}:{target_id}"
            )
        ]
        for target_id, label in members
    ]
    rows.append(
        [InlineKeyboardButton(text=texts.CIRCLE_BACK_BUTTON_LABEL, callback_data=f"crc:main:{owner_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def circle_remove_confirm_keyboard(owner_id: int, target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.CONFIRM_YES, callback_data=f"crc:remove_confirm:{owner_id}:{target_id}"
                ),
                InlineKeyboardButton(text=texts.CONFIRM_NO, callback_data=f"crc:remove_cancel:{owner_id}"),
            ]
        ]
    )
