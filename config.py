# config.py
from dotenv import load_dotenv
import os

# Загружаем переменные окружения из .env
load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")

# FFmpeg (полный путь к бинарю)
FFMPEG_PATH = os.getenv("FFMPEG_PATH")

# Файл меню по умолчанию
MENU_FILE = os.getenv("MENU_FILE", "menu.json")

# Провайдер LLM: 'openai' или 'mistral'
PROVIDER = os.getenv("PROVIDER", "openai").lower()

# --- OpenAI settings ---
# Список API-ключей (comma-separated)
_OPENAI_KEYS = os.getenv("OPENAI_API_KEYS", "")
OPENAI_API_KEYS = [k.strip() for k in _OPENAI_KEYS.split(",") if k.strip()]

# Список моделей (comma-separated)
_OPENAI_MODELS = os.getenv("OPENAI_MODELS", "")
OPENAI_MODELS = [m.strip() for m in _OPENAI_MODELS.split(",") if m.strip()]

# Список базовых URL (comma-separated)
_OPENAI_BASES = os.getenv("OPENAI_API_BASE_URLS", "")
OPENAI_API_BASE_URLS = [u.strip() for u in _OPENAI_BASES.split(",") if u.strip()]

# --- Mistral settings ---
# Список API-ключей (comma-separated)
_MISTRAL_KEYS = os.getenv("MISTRAL_API_KEYS", "")
MISTRAL_API_KEYS = [k.strip() for k in _MISTRAL_KEYS.split(",") if k.strip()]

# Список моделей (comma-separated)
_MISTRAL_MODELS = os.getenv("MISTRAL_MODELS", "")
MISTRAL_MODELS = [m.strip() for m in _MISTRAL_MODELS.split(",") if m.strip()]

# Список базовых URL (comma-separated)
_MISTRAL_BASES = os.getenv("MISTRAL_API_BASE_URLS", "")
MISTRAL_API_BASE_URLS = [u.strip() for u in _MISTRAL_BASES.split(",") if u.strip()]
