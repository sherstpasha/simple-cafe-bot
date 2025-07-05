import logging
from aiogram import Router
from aiogram.types import ChatMemberUpdated

router = Router()
logger = logging.getLogger(__name__)


@router.my_chat_member()
async def on_bot_added(update: ChatMemberUpdated):
    """
    Срабатывает при изменении статуса бота в каком-то чате.
    Когда бот добавлен в группу — new_chat_member.status будет 'member' или 'administrator'.
    """
    old, new = update.old_chat_member, update.new_chat_member
    # Проверяем, что до этого бот не был участником, а теперь стал
    if old.status in ("left", "kicked") and new.status in ("member", "administrator"):
        chat = update.chat
        logger.info(
            f"✅ Бот добавлен в чат «{chat.title or chat.id}», chat_id = {chat.id}"
        )
