# config.py
from dotenv import load_dotenv
import os

# Загружаем переменные окружения из .env
load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

# FFmpeg (полный путь к бинарю)
FFMPEG_PATH = os.getenv("FFMPEG_PATH")

# Файл меню по умолчанию
MENU_FILE = os.getenv("MENU_FILE", "menu.json")

# OpenAI параметры
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "EMPTY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "")
