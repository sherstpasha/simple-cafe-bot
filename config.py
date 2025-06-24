from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FFMPEG_PATH = os.getenv("FFMPEG_PATH")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL")
MENU_FILE = os.getenv("MENU_FILE", "menu.json")
