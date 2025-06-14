from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from reports import generate_reports
from utils import send_main_menu, user_last_bot_message

from datetime import datetime, timedelta

router = Router()


@router.callback_query(F.data == "report")
async def choose_period(call: CallbackQuery, state: FSMContext, bot):
    await state.clear()

    # Удалить предыдущее меню
    last_msg_id = user_last_bot_message.get(call.from_user.id)
    if last_msg_id:
        try:
            await bot.delete_message(call.message.chat.id, last_msg_id)
        except Exception:
            pass

    # Показать кнопки выбора периода
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 За сегодня", callback_data="report_today")],
            [
                InlineKeyboardButton(
                    text="📆 За вчера", callback_data="report_yesterday"
                )
            ],
            [InlineKeyboardButton(text="🗓 За всё время", callback_data="report_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_report")],
        ]
    )
    await call.message.answer("📊 Выберите период для отчёта:", reply_markup=kb)


@router.callback_query(F.data.in_({"report_today", "report_yesterday", "report_all"}))
async def generate_selected_report(call: CallbackQuery, state: FSMContext, bot):
    today = datetime.now().date()
    if call.data == "report_today":
        start_date = end_date = today
    elif call.data == "report_yesterday":
        start_date = end_date = today - timedelta(days=1)
    else:
        start_date = end_date = None  # Без фильтра

    # Удалить сообщение с выбором периода
    try:
        await call.message.delete()
    except Exception:
        pass

    # Генерация отчёта с фильтрами
    report_path, log_path = generate_reports(start_date, end_date)

    await call.message.answer_document(document=FSInputFile(report_path))
    await call.message.answer_document(document=FSInputFile(log_path))

    await send_main_menu(call.from_user.id, call.message.chat.id, bot)


@router.callback_query(F.data == "cancel_report")
async def cancel_report(call: CallbackQuery, state: FSMContext, bot):
    await state.clear()
    await send_main_menu(call.from_user.id, call.message.chat.id, bot)
