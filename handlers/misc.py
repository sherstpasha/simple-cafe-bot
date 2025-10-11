import logging
from aiogram import Router, F
from aiogram.types import Message

router = Router()


@router.message(F.chat.type == "private")
async def delete_all(message: Message):
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"⚠️ Не удалось удалить сообщение: {e}")
