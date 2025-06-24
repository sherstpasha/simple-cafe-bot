import os
import logging
from datetime import datetime

import speech_recognition as sr
from pydub import AudioSegment
import httpx  # для перехвата HTTP-ошибок

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from mistralai import Mistral

from config import FFMPEG_PATH, MISTRAL_API_KEY, MISTRAL_MODEL
from states import OrderFSM
from db import add_order
from utils import edit_or_send, user_last_bot_message
from handlers.menu import get_main_menu

# Настройка ffmpeg
os.environ["PATH"] += os.pathsep + FFMPEG_PATH
AudioSegment.converter = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
AudioSegment.ffprobe = os.path.join(FFMPEG_PATH, "ffprobe.exe")

mistral_client = Mistral(api_key=MISTRAL_API_KEY)
router = Router()
logger = logging.getLogger(__name__)


@router.message(F.voice)
async def handle_voice_message(message: Message, bot, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id

    logger.info(f"[Voice received] from {user_id}")

    # 1) Удаляем само голосовое сообщение
    try:
        await message.delete()
    except Exception:
        pass

    # 2) Удаляем предыдущее меню (если было)
    prev_msg_id = user_last_bot_message.get(user_id)
    if prev_msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=prev_msg_id)
        except Exception:
            pass

    # 3) Скачиваем и конвертируем в WAV
    voice = await bot.download(message.voice.file_id)
    ogg_path = f"voice_{message.message_id}.ogg"
    wav_path = f"voice_{message.message_id}.wav"
    with open(ogg_path, "wb") as f:
        f.write(voice.read())
    audio = AudioSegment.from_file(ogg_path)
    audio.export(wav_path, format="wav")

    try:
        # 4) Распознаём Google Speech
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as src:
            audio_data = recognizer.record(src)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
        logger.info(f"[Voice recognized]: {text}")

        # 5) Посылаем текст в Mistral
        response = mistral_client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помогаешь принимать заказы в кафе. "
                        "Из голоса нужно достать item_name и payment_type."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        reply = response.choices[0].message.content.strip()
        logger.info(f"[Mistral reply] {reply}")

        # 6) Парсим ответ
        item_name = ""
        payment_type = ""
        for line in reply.splitlines():
            if line.startswith("item_name"):
                item_name = line.split(":", 1)[1].strip()
            elif line.startswith("payment_type"):
                payment_type = line.split(":", 1)[1].strip()

        if not item_name or not payment_type:
            raise ValueError("Пустой item_name/payment_type")

        # 7) Переход к подтверждению
        await state.update_data(item_name=item_name, payment_type=payment_type)
        await state.set_state(OrderFSM.awaiting_add_confirmation)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Добавить", callback_data="confirm_add"
                    ),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add"),
                ]
            ]
        )
        msg = await bot.send_message(
            chat_id, f"🔹 Добавить «{payment_type}, {item_name}»?", reply_markup=kb
        )
        user_last_bot_message[user_id] = msg.message_id

    except sr.UnknownValueError:
        await bot.send_message(
            chat_id, "🗣 Не удалось распознать речь, попробуйте ещё раз."
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            await bot.send_message(
                chat_id, "⚠️ Слишком много запросов, подождите минуту."
            )
        else:
            await bot.send_message(chat_id, "⚠️ Сервис недоступен, попробуйте позже.")
    except Exception:
        logger.exception("Error in voice handler")
        await bot.send_message(chat_id, "❌ Ошибка обработки, попробуйте позже.")
    finally:
        # 8) Убираем временные файлы
        for path in (ogg_path, wav_path):
            try:
                os.remove(path)
            except OSError:
                pass
