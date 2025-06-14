from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from utils import user_last_bot_message

router = Router()


def get_main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔘 Добавить", callback_data="add")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data="delete")],
            [InlineKeyboardButton(text="📄 Получить отчёт", callback_data="report")],
        ]
    )


@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = get_main_menu()
    msg = await message.answer("Выберите действие:", reply_markup=kb)
    user_last_bot_message[message.from_user.id] = msg.message_id
