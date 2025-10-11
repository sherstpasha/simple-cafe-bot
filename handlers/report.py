from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from reports import generate_reports
from keyboards import show_main_menu
from utils import user_last_bot_message, check_membership, notify_temp
from datetime import datetime, timedelta

router = Router()


@router.callback_query(F.message.chat.type == "private", F.data == "report")
async def choose_period(call: CallbackQuery, state: FSMContext, bot):
    if not await check_membership(bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    await state.clear()
    last = user_last_bot_message.get(call.from_user.id)
    if last:
        try:
            await bot.delete_message(call.message.chat.id, last)
        except:
            pass

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


@router.callback_query(
    F.message.chat.type == "private",
    F.data.in_({"report_today", "report_yesterday", "report_all"}),
)
async def generate_selected_report(call: CallbackQuery, state: FSMContext, bot):
    if not await check_membership(bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    today = datetime.now().date()
    if call.data == "report_today":
        start, end = today, today
    elif call.data == "report_yesterday":
        start, end = today - timedelta(days=1), today - timedelta(days=1)
    else:
        start = end = None

    try:
        await call.message.delete()
    except:
        pass

    report_path, staff_report_path, log_path = generate_reports(start, end)

    await call.message.answer_document(FSInputFile(report_path))
    if staff_report_path:
        await call.message.answer_document(FSInputFile(staff_report_path))
    await call.message.answer_document(FSInputFile(log_path))
    await show_main_menu(call.from_user.id, call.message.chat.id, bot)


@router.callback_query(F.message.chat.type == "private", F.data == "cancel_report")
async def cancel_report(call: CallbackQuery, state: FSMContext, bot):
    if not await check_membership(bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    await show_main_menu(call.from_user.id, call.message.chat.id, bot)
