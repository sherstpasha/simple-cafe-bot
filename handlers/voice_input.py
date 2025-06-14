import os
import speech_recognition as sr
from aiogram import Router, F
from aiogram.types import Message
from config import FFMPEG_PATH

# Добавляем путь к ffmpeg в системный PATH
os.environ["PATH"] += os.pathsep + FFMPEG_PATH

from pydub import AudioSegment

# Указываем ffmpeg и ffprobe
AudioSegment.converter = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
AudioSegment.ffprobe = os.path.join(FFMPEG_PATH, "ffprobe.exe")

print("FFmpeg path:", AudioSegment.converter)
print("FFprobe path:", AudioSegment.ffprobe)

router = Router()


@router.message(F.voice)
async def handle_voice_message(message: Message, bot):
    print(f"[Voice received] from {message.from_user.id}")

    voice = await bot.download(message.voice.file_id)
    ogg_path = f"voice_{message.message_id}.ogg"
    wav_path = f"voice_{message.message_id}.wav"

    with open(ogg_path, "wb") as f:
        f.write(voice.read())

    try:
        audio = AudioSegment.from_file(ogg_path)
        audio.export(wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data, language="ru-RU")
                print(f"[Voice recognized] User {message.from_user.id}: {text}")
            except sr.UnknownValueError:
                print("[!] Не удалось распознать голосовое сообщение")
    finally:
        # Гарантированное удаление файлов
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)

    # Удаление самого голосового сообщения из чата
    try:
        await message.delete()
    except Exception as e:
        print(f"[!] Не удалось удалить сообщение: {e}")
