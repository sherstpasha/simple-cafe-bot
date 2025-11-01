# config.py
from dotenv import load_dotenv
import os
import logging

# Загружаем переменные окружения из .env
load_dotenv()

logger = logging.getLogger(__name__)

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
BOT_OWNER_ID_STR = os.getenv("BOT_OWNER_ID")

# Преобразуем BOT_OWNER_ID в int если возможно
BOT_OWNER_ID = None
if BOT_OWNER_ID_STR:
    try:
        BOT_OWNER_ID = int(BOT_OWNER_ID_STR)
    except ValueError:
        logger.warning(f"BOT_OWNER_ID is not a valid integer: {BOT_OWNER_ID_STR}")

# Проверка обязательных переменных
if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set in environment variables!")
if not GROUP_CHAT_ID:
    logger.warning("GROUP_CHAT_ID is not set - notifications will not be sent to group!")

# FFmpeg (опционально: путь к бинарю, если он не доступен в PATH)
FFMPEG_PATH = os.getenv("FFMPEG_PATH")

# Файл меню по умолчанию
MENU_FILE = os.getenv("MENU_FILE", "menu.json")

# OpenAI параметры
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "EMPTY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "")

if not OPENAI_MODEL:
    logger.warning("OPENAI_MODEL is not set - LLM functionality may not work!")

