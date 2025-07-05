# bot.py

import logging
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN
from db import init_db
from keyboards import show_main_menu

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
    await state.clear()
    await show_main_menu(message.from_user.id, message.chat.id, bot)


# Точка входа
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
