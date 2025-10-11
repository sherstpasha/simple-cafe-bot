from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import json

from config import MENU_FILE
from utils import edit_or_send, check_membership, notify_temp
from keyboards import get_main_menu

router = Router()

with open(MENU_FILE, encoding="utf-8") as f:
    MENU = json.load(f)
MAIN_MENU = MENU.get("main", {})
ADDONS = MENU.get("addons", {})


def build_menu_text() -> str:
    lines = ["📋 <b>Наше меню:</b>"]
    for item, price in MAIN_MENU.items():
        lines.append(f"• {item} — {price}₽")
    if ADDONS:
        lines.append("\n➕ <b>Добавки:</b>")
        for addon, price in ADDONS.items():
            lines.append(f"• {addon} — {price}₽" if price else f"• {addon} — бесплатно")
    return "\n".join(lines)


@router.callback_query(F.message.chat.type == "private", F.data == "show_menu")
async def show_menu(call: CallbackQuery):
    await call.answer()
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    text = build_menu_text()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="main_menu")],
        ]
    )
    await edit_or_send(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text=text,
        reply_markup=kb,
    )


@router.callback_query(F.message.chat.type == "private", F.data == "main_menu")
async def back_to_main(call: CallbackQuery):
    await call.answer()
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    # просто показываем обновлённую главную клавиатуру
    await edit_or_send(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text="Напишите заказ и тип оплаты:",
        reply_markup=get_main_menu(),
    )
