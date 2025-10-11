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
            [InlineKeyboardButton(text="📋 Обычные заказы", callback_data="report_type_regular")],
            [InlineKeyboardButton(text="👥 Заказы сотрудников", callback_data="report_type_staff")],
            [InlineKeyboardButton(text="📊 Все отчеты", callback_data="report_type_all")],
            [InlineKeyboardButton(text="�� Назад", callback_data="cancel_report")],
        ]
    )
    await call.message.answer("📊 Выберите тип отчёта:", reply_markup=kb)


@router.callback_query(
    F.message.chat.type == "private",
    F.data.in_({"report_type_regular", "report_type_staff", "report_type_all"}),
)
async def choose_report_period(call: CallbackQuery, state: FSMContext):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    
    report_type = call.data.split("_")[-1]  # regular, staff, all
    await state.update_data(report_type=report_type)
    
    if report_type == "regular":
        type_text = "обычных заказов"
    elif report_type == "staff":
        type_text = "заказов сотрудников"
    else:
        type_text = "всех заказов"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 За сегодня", callback_data="period_today")],
            [InlineKeyboardButton(text="📆 За вчера", callback_data="period_yesterday")],
            [InlineKeyboardButton(text="🗓 За всё время", callback_data="period_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="report")],
        ]
    )
    await call.message.edit_text(f"📊 Выберите период для отчёта {type_text}:", reply_markup=kb)


@router.callback_query(
    F.message.chat.type == "private",
    F.data.in_({"period_today", "period_yesterday", "period_all"}),
)
async def generate_selected_report(call: CallbackQuery, state: FSMContext, bot):
    if not await check_membership(bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    
    data = await state.get_data()
    report_type = data.get("report_type", "regular")
    
    today = datetime.now().date()
    if call.data == "period_today":
        start, end = today, today
    elif call.data == "period_yesterday":
        start, end = today - timedelta(days=1), today - timedelta(days=1)
    else:
        start = end = None

    try:
        await call.message.delete()
    except:
        pass

    report_path, staff_report_path, log_path = generate_reports(start, end)
    
    if report_type == "staff":
        if staff_report_path:
            await call.message.answer_document(FSInputFile(staff_report_path))
        else:
            await call.message.answer("📊 Нет заказов сотрудников за выбранный период.")
    elif report_type == "regular":
        await call.message.answer_document(FSInputFile(report_path))
    else:  # all
        await call.message.answer_document(FSInputFile(report_path))
        if staff_report_path:
            await call.message.answer_document(FSInputFile(staff_report_path))
    
    await call.message.answer_document(FSInputFile(log_path))
    await state.clear()
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
