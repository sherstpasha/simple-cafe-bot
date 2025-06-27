# keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import send_and_track
from db import get_user_role


def confirm_keyboard(
    confirm_text: str, confirm_cb: str, cancel_cb: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=confirm_text, callback_data=confirm_cb)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb)],
        ]
    )


def get_main_menu(user_id: int) -> InlineKeyboardMarkup:
    """
    Формирует клавиатуру главного меню в зависимости от роли пользователя:
    - Для «Стою на кассе»: [Сменить роль], [Удалить, Получить отчёт]
    - Для всех остальных: [Сменить роль]
    """
    role = get_user_role(user_id)

    # Собираем ряды кнопок
    keyboard = []

    # 1-й ряд — всегда
    keyboard.append(
        [InlineKeyboardButton(text="🎭 Сменить роль", callback_data="change_role")]
    )

    # 2-й ряд — только для кассира
    if role == "Стою на кассе":
        keyboard.append(
            [
                InlineKeyboardButton(text="❌ Удалить", callback_data="delete"),
                InlineKeyboardButton(text="📄 Получить отчёт", callback_data="report"),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def show_main_menu(user_id: int, chat_id: int, bot):
    """
    Отправляет или обновляет сообщение с основным меню,
    включая подпись текущей роли.
    """
    role = get_user_role(user_id)
    text = f"Ваша роль: <b>{role}</b>\nВыберите действие:"
    kb = get_main_menu(user_id)
    await send_and_track(bot, user_id, chat_id, text, reply_markup=kb)
