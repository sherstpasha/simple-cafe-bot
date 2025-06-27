# handlers/misc.py

import logging
from aiogram import Router
from aiogram.types import Message
from db import get_user_role

router = Router()


@router.message()
async def delete_all(message: Message):
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"⚠️ Не удалось удалить сообщение: {e}")
