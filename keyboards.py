# keyboard.py

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import send_and_track


def confirm_keyboard(
    confirm_text: str, confirm_cb: str, cancel_cb: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=confirm_text, callback_data=confirm_cb)],
            [InlineKeyboardButton(text="👥 Для сотрудника", callback_data="confirm_add_staff")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb)],
        ]
    )


def get_main_menu() -> InlineKeyboardMarkup:
    # Основное меню действий: показать меню, удалить заказы, получить отчёт
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Меню", callback_data="show_menu")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data="delete")],
            [InlineKeyboardButton(text="📄 Получить отчёт", callback_data="report")],
        ]
    )


async def show_main_menu(user_id: int, chat_id: int, bot: Bot):
    kb = get_main_menu()
    await send_and_track(
        bot, user_id, chat_id, "Напишите заказ и тип оплаты:", reply_markup=kb
    )
