# keyboards.py

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import user_last_bot_message


def confirm_keyboard(
    confirm_text: str, confirm_cb: str, cancel_cb: str
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру подтверждения с кнопками "✅" и "❌".
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=confirm_text, callback_data=confirm_cb)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb)],
        ]
    )


async def show_main_menu(user_id: int, chat_id: int, bot: Bot):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить", callback_data="delete")],
            [InlineKeyboardButton(text="📄 Получить отчёт", callback_data="report")],
        ]
    )
    msg = await bot.send_message(chat_id, "Выберите действие:", reply_markup=kb)
    user_last_bot_message[user_id] = msg.message_id
