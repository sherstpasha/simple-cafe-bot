from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db import set_user_role, get_user_role
from keyboards import show_main_menu

router = Router()


@router.callback_query(F.data == "change_role")
async def choose_role(call: CallbackQuery):
    current = get_user_role(call.from_user.id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Стою на кассе", callback_data="role_cashier"
                ),
                InlineKeyboardButton(text="Готовлю", callback_data="role_cook"),
                InlineKeyboardButton(text="Отдыхаю", callback_data="role_rest"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_role")],
        ]
    )
    # Вместо call.message.answer/edit, просто правим старое
    await call.message.edit_text(
        f"Текущая роль: <b>{current}</b>\nВыберите новую:",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.startswith("role_"))
async def set_role(call: CallbackQuery):
    mapping = {
        "role_cashier": "Стою на кассе",
        "role_cook": "Готовлю",
        "role_rest": "Отдыхаю",
    }
    new = mapping[call.data]
    set_user_role(call.from_user.id, call.from_user.username or "", new)
    await call.answer(f"Роль изменена на «{new}»", show_alert=True)
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


@router.callback_query(F.data == "cancel_role")
async def cancel_role(call: CallbackQuery):
    await call.answer()
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
