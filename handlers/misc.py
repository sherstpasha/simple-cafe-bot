import logging
from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def delete_all_except_voice(message: Message):
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"⚠️ Не удалось удалить сообщение: {e}")
