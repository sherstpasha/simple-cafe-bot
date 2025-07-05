from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import json

from config import MENU_FILE
from utils import edit_or_send
from keyboards import get_main_menu

router = Router()

# Загрузка меню из JSON
with open(MENU_FILE, encoding="utf-8") as f:
    MENU = json.load(f)
MAIN_MENU = MENU.get("main", {})
ADDONS = MENU.get("addons", {})


# Функция формирования текста меню
def build_menu_text() -> str:
    lines = ["📋 <b>Наше меню:</b>"]
    for item, price in MAIN_MENU.items():
        lines.append(f"• {item} — {price}₽")
    if ADDONS:
        lines.append("\n➕ <b>Добавки:</b>")
        for addon, price in ADDONS.items():
            price_text = f"{price}₽" if price else "бесплатно"
            lines.append(f"• {addon} — {price_text}")
    return "\n".join(lines)


@router.callback_query(F.chat.type == "private", F.data == "show_menu")
async def show_menu(call: CallbackQuery):
    await call.answer()
    text = build_menu_text()
    # Клавиатура с кнопкой назад
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="main_menu")],
        ]
    )
    # Заменяем текущее сообщение меню
    await edit_or_send(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text=text,
        reply_markup=kb,
    )


@router.callback_query(F.chat.type == "private", F.data == "main_menu")
async def back_to_main(call: CallbackQuery):
    await call.answer()
    # Возвращаем главное меню
    await edit_or_send(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text="Выберите действие:",
        reply_markup=get_main_menu(),
    )
