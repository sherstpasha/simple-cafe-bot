import logging
from aiogram.types import InlineKeyboardMarkup
from aiogram import Bot

user_last_bot_message = {}


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
