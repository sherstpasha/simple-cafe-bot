import logging
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from db import add_order, init_db

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

init_db()


# FSM состояния
class OrderFSM(StatesGroup):
    awaiting_payment_type = State()
    awaiting_item_name = State()
    awaiting_add_confirmation = State()


# Хранилище для последнего сообщения бота
user_last_bot_message = {}


# Главное меню
async def send_main_menu(user_id, chat_id):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔘 Добавить", callback_data="add")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data="delete")],
            [InlineKeyboardButton(text="📄 Получить отчёт", callback_data="report")],
        ]
    )
    msg = await bot.send_message(chat_id, "Выберите действие:", reply_markup=kb)
    user_last_bot_message[user_id] = msg.message_id


# Редактировать предыдущее сообщение бота
async def edit_or_send(user_id, chat_id, text, reply_markup=None):
    last_msg_id = user_last_bot_message.get(user_id)
    try:
        if last_msg_id:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=last_msg_id,
                reply_markup=reply_markup,
            )
        else:
            msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
            user_last_bot_message[user_id] = msg.message_id
    except Exception as e:
        logging.warning(f"⚠️ Не удалось отредактировать сообщение: {e}")


# /start
@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await send_main_menu(message.from_user.id, message.chat.id)


# ➕ Шаг 1 — Выбор типа оплаты
@router.callback_query(F.data == "add")
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.awaiting_payment_type)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Наличный", callback_data="pay_cash")],
            [InlineKeyboardButton(text="Безналичный", callback_data="pay_card")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_add")],
        ]
    )
    await edit_or_send(
        call.from_user.id, call.message.chat.id, "🔹 Выберите тип оплаты:", kb
    )


# ➕ Шаг 2 — Ввод названия
@router.callback_query(F.data.in_(["pay_cash", "pay_card"]))
async def payment_type_selected(call: CallbackQuery, state: FSMContext):
    payment = "Наличный" if call.data == "pay_cash" else "Безналичный"
    await state.update_data(payment_type=payment)
    await state.set_state(OrderFSM.awaiting_item_name)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="add")],
        ]
    )
    await edit_or_send(
        call.from_user.id,
        call.message.chat.id,
        f"🔹 Тип оплаты: {payment}, введите название напитка или десерта:",
        kb,
    )


# ➕ Шаг 2 — Обработка текста
@router.message(OrderFSM.awaiting_item_name)
async def item_name_entered(message: Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)
    await state.update_data(item_name=message.text)
    data = await state.get_data()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Добавить", callback_data="confirm_add")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")],
        ]
    )
    await state.set_state(OrderFSM.awaiting_add_confirmation)
    await edit_or_send(
        message.from_user.id,
        message.chat.id,
        f"🔹 Добавить «{data['payment_type']}, {data['item_name']}»?",
        kb,
    )


# ➕ Шаг 3 — Подтверждение
@router.callback_query(F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    add_order(
        payment_type=data["payment_type"],
        item_name=data["item_name"],
        user_id=call.from_user.id,
        username=call.from_user.username or "",
    )
    await bot.send_message(
        call.message.chat.id,
        f"✅ Запись от {now}, {data['payment_type']}, {data['item_name']} добавлена.",
    )
    await state.clear()
    await bot.delete_message(call.message.chat.id, call.message.message_id)
    await send_main_menu(call.from_user.id, call.message.chat.id)


# ⛔ Отмена (Назад из любого места)
@router.callback_query(F.data == "cancel_add")
async def cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await bot.delete_message(call.message.chat.id, call.message.message_id)
    await send_main_menu(call.from_user.id, call.message.chat.id)


# 🧹 Удаление всех других сообщений пользователя
@router.message()
async def clean_unexpected_messages(message: Message):
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logging.warning(f"⚠️ Не удалось удалить сообщение пользователя: {e}")


# Запуск
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
