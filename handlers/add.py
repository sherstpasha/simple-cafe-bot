import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from states import OrderFSM
from db import add_order
from utils import edit_or_send, user_last_bot_message

router = Router()


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
        call.bot, call.from_user.id, call.message.chat.id, "🔹 Выберите тип оплаты:", kb
    )


@router.callback_query(F.data.in_(["pay_cash", "pay_card"]))
async def payment_type_selected(call: CallbackQuery, state: FSMContext):
    payment = "Наличный" if call.data == "pay_cash" else "Безналичный"
    await state.update_data(payment_type=payment)
    await state.set_state(OrderFSM.awaiting_item_name)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="add")]]
    )
    await edit_or_send(
        call.bot,
        call.from_user.id,
        call.message.chat.id,
        f"🔹 Тип оплаты: {payment}, введите название напитка или десерта:",
        kb,
    )


@router.message(OrderFSM.awaiting_item_name)
async def item_name_entered(message: Message, state: FSMContext):
    await message.delete()
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
        message.bot,
        message.from_user.id,
        message.chat.id,
        f"🔹 Добавить «{data['payment_type']}, {data['item_name']}»?",
        kb,
    )


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
    await call.message.answer(
        f"✅ Запись от {now}, {data['payment_type']}, {data['item_name']} добавлена."
    )
    await state.clear()
    await call.message.delete()
    from handlers.menu import get_main_menu

    kb = get_main_menu()
    msg = await call.message.answer("Выберите действие:", reply_markup=kb)
    user_last_bot_message[call.from_user.id] = msg.message_id


@router.callback_query(F.data == "cancel_add")
async def cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    from handlers.menu import get_main_menu

    kb = get_main_menu()
    msg = await call.message.answer("Выберите действие:", reply_markup=kb)
    user_last_bot_message[call.from_user.id] = msg.message_id
