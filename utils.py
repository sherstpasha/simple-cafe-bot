import os
import logging
from aiogram.types import InlineKeyboardMarkup
from aiogram import Bot
from aiogram.types import Message, CallbackQuery

import speech_recognition as sr
from pydub import AudioSegment

import asyncio

from config import FFMPEG_PATH
from config import GROUP_CHAT_ID, BOT_OWNER_ID

# Глобальный словарь для хранения последних сообщений
user_last_bot_message = {}

# Настройка путей к ffmpeg
os.environ["PATH"] += os.pathsep + FFMPEG_PATH
AudioSegment.converter = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
AudioSegment.ffprobe = os.path.join(FFMPEG_PATH, "ffprobe.exe")

logger = logging.getLogger(__name__)


async def edit_or_send(
    bot: Bot,
    user_id: int,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup = None,
):
    last_msg_id = user_last_bot_message.get(user_id)
    try:
        if last_msg_id:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=last_msg_id,
                reply_markup=reply_markup,
            )
        else:
            msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
            user_last_bot_message[user_id] = msg.message_id
    except Exception as e:
        logging.warning(f"⚠️ Не удалось отредактировать сообщение: {e}")


async def transcribe_voice(bot: Bot, message) -> str | None:
    """
    Преобразует голосовое сообщение в текст.
    Возвращает строку текста или None при неудаче.
    """
    try:
        voice = await bot.download(message.voice.file_id)
        ogg_path = f"voice_{message.message_id}.ogg"
        wav_path = f"voice_{message.message_id}.wav"
        with open(ogg_path, "wb") as f:
            f.write(voice.read())

        audio = AudioSegment.from_file(ogg_path)
        audio.export(wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as src:
            audio_data = recognizer.record(src)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
        return text

    except sr.UnknownValueError:
        logger.warning("Не удалось распознать речь")
        return None
    except Exception as e:
        logger.exception("Ошибка при распознавании голоса")
        return None
    finally:
        for path in (ogg_path, wav_path):
            try:
                os.remove(path)
            except OSError:
                pass


async def send_and_track(
    bot: Bot, user_id: int, chat_id: int, text: str, **kwargs
) -> Message:
    """
    Отправляет сообщение и обновляет словарь user_last_bot_message.
    """
    msg = await bot.send_message(chat_id, text, **kwargs)
    user_last_bot_message[user_id] = msg.message_id
    return msg


async def notify_temp(target: Message | CallbackQuery, text: str, delay: int = 4):
    """
    Показывает временное уведомление:
    - Если target — CallbackQuery, вызывает call.answer (toast).
    - Если target — Message, отправляет сообщение и удаляет его через delay секунд.
    """
    if isinstance(target, CallbackQuery):
        # показа "тоста" без alert-а
        await target.answer(text, show_alert=False)
    else:
        # временное сообщение под чистку
        msg = await target.answer(text, disable_notification=True)
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except:
            pass


async def check_membership(bot, user_id: int) -> bool:
    """
    Возвращает True, если пользователь user_id:
      • владелец бота (BOT_OWNER_ID), или
      • состоит в группе GROUP_CHAT_ID (member/creator/administrator).
    Иначе False.
    """
    if user_id == BOT_OWNER_ID:
        return True

    try:
        mem = await bot.get_chat_member(GROUP_CHAT_ID, user_id)
        return mem.status in ("member", "creator", "administrator")
    except:
        return False
