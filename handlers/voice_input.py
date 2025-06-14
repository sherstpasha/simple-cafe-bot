import os
import speech_recognition as sr
from pydub import AudioSegment
from aiogram import Router, F
from aiogram.types import Message

router = Router()


@router.message(F.voice)
async def handle_voice_message(message: Message, bot):
    print(f"[Voice received] from {message.from_user.id}")
    # Скачиваем голосовое сообщение
    voice = await bot.download(message.voice.file_id)
    ogg_path = f"voice_{message.message_id}.ogg"
    wav_path = f"voice_{message.message_id}.wav"

    with open(ogg_path, "wb") as f:
        f.write(voice.read())

    # Конвертация .ogg → .wav
    audio = AudioSegment.from_file(ogg_path)
    audio.export(wav_path, format="wav")

    # Распознавание через Google
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            print(f"[Voice recognized] User {message.from_user.id}: {text}")
        except sr.UnknownValueError:
            print("[!] Не удалось распознать голосовое сообщение")

    # Очистка временных файлов
    os.remove(ogg_path)
    os.remove(wav_path)
