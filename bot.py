# bot.py

import logging
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, GROUP_CHAT_ID
from db import init_db
from keyboards import show_main_menu
from utils import send_and_track

# Роутеры
from handlers import add, delete, report, misc, menu, chat_events

# Настройка логгирования и базы данных
logging.basicConfig(level=logging.INFO)
init_db()

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# Подключение роутеров
dp.include_router(add.router)
dp.include_router(delete.router)
dp.include_router(report.router)
dp.include_router(misc.router)
dp.include_router(menu.router)
dp.include_router(chat_events.router)


# Обработка команды /start
@dp.message(F.chat.type == "private", F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    # очищаем предыдущее состояние
    await state.clear()

    # 1) Приветственная инструкция
    welcome = (
        "👋 Привет! Я — помощник кассира.\n\n"
        "Как пользоваться:\n"
        "• Отправляйте текстовые или голосовые сообщения с вашими заказами.\n"
        "  Языковая модель разберёт их и соберу для вас структурированный заказ.\n"
        "• Все оформленные заказы будут пересылаться в группу бариста.\n"
        "• Удаляйте свои заказы кнопкой «❌ Удалить».\n"
        "• Генерируйте отчёты кнопкой «📄 Получить отчёт».\n\n"
        "Поехали!"
    )
    await send_and_track(bot, message.from_user.id, message.chat.id, welcome)

    # 2) Главная клавиатура
    await show_main_menu(message.from_user.id, message.chat.id, bot)


async def _log_configured_chats() -> None:
    raw_ids = (GROUP_CHAT_ID or "").split(",")
    chat_ids = [cid.strip() for cid in raw_ids if cid.strip()]

    if not chat_ids:
        logging.warning("GROUP_CHAT_ID is not configured; бот не знает целевые чаты.")
        return

    for raw_id in chat_ids:
        chat_id: int | str = raw_id
        if raw_id.lstrip("-+").isdigit():
            try:
                chat_id = int(raw_id)
            except ValueError:
                pass
        try:
            chat = await bot.get_chat(chat_id)
            logging.info(
                "✅ Бот активен в чате '%s' (id=%s, type=%s)",
                chat.title or chat.id,
                chat.id,
                chat.type,
            )
        except Exception as exc:
            logging.warning("⚠️ Не удалось получить чат %s: %s", raw_id, exc)


# Точка входа
async def main():
    await _log_configured_chats()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
