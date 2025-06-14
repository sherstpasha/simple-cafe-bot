# handlers/report.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from reports import generate_reports
from utils import send_main_menu, user_last_bot_message

router = Router()


@router.callback_query(F.data == "report")
async def send_reports(call: CallbackQuery, state: FSMContext, bot):
    await state.clear()

    # Удаляем старое меню, если есть
    last_msg_id = user_last_bot_message.get(call.from_user.id)
    if last_msg_id:
        try:
            await bot.delete_message(call.message.chat.id, last_msg_id)
        except Exception:
            pass

    # Генерация отчётов
    report_path, log_path = generate_reports()
    await call.message.answer_document(document=FSInputFile(report_path))
    await call.message.answer_document(document=FSInputFile(log_path))

    # Новое меню
    await send_main_menu(call.from_user.id, call.message.chat.id, bot)
