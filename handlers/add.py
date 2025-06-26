# handlers/add.py

import json
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from mistralai import Mistral
from config import MENU_FILE, MISTRAL_API_KEY, MISTRAL_MODEL
from db import add_order
from utils import edit_or_send, transcribe_voice
from keyboards import show_main_menu, confirm_keyboard


router = Router()
logger = logging.getLogger(__name__)

# Загружаем меню
with open(MENU_FILE, encoding="utf-8") as f:
    MENU_MAP = json.load(f)

mistral_client = Mistral(api_key=MISTRAL_API_KEY)


# ——————— ОБРАБОТКА ЛЮБОГО СООБЩЕНИЯ: текст или голос ———————
@router.message()
async def handle_message(message: Message, state: FSMContext, bot):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Удаляем сообщение от пользователя (опционально)
        try:
            await message.delete()
        except Exception:
            pass

        # Получаем текст
        if message.voice:
            user_text = await transcribe_voice(bot, message)
            if not user_text:
                await bot.send_message(
                    chat_id, "🗣 Не удалось распознать речь, попробуйте ещё раз."
                )
                return
        else:
            user_text = message.text.strip()

        logger.info(f"[User Input]: {user_text}")

        # Подготовим меню в виде текста
        menu_text = "\n".join(f"- {k}" for k in MENU_MAP.keys())

        # Обращение к LLM
        response = mistral_client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помогаешь принимать заказы в кафе.\n"
                        "Из сообщения пользователя нужно достать `item_name` и `payment_type`.\n"
                        "Ответь строго в формате:\n\n"
                        "item_name: <название>\npayment_type: <наличный или безналичный>"
                    ),
                },
                {"role": "user", "content": user_text},
            ],
        )

        reply = response.choices[0].message.content.strip()
        logger.info(f"[LLM reply]: {reply}")

        # Извлечение полей
        item_name = ""
        payment_type = ""
        for line in reply.splitlines():
            if line.lower().startswith("item_name"):
                item_name = line.split(":", 1)[1].strip()
            elif line.lower().startswith("payment_type"):
                payment_type = line.split(":", 1)[1].strip()

        if not item_name or not payment_type:
            raise ValueError("item_name или payment_type не получены")

        # Поиск в MENU_MAP
        matched_key = next(
            (k for k in MENU_MAP if item_name.lower() in k.lower()), None
        )
        if not matched_key:
            raise ValueError("Позиция не найдена в меню")

        price = MENU_MAP[matched_key]
        category = matched_key.split(":")[0].strip() if ":" in matched_key else ""
        item_name_clean = (
            matched_key.split(":")[1].strip()
            if ":" in matched_key
            else matched_key.strip()
        )

        await state.update_data(
            item_name=item_name_clean,
            category=category,
            payment_type=payment_type,
            price=price,
        )
        await state.set_state("awaiting_add_confirmation")

        # Клавиатура подтверждения
        kb = confirm_keyboard("✅ Добавить", "confirm_add", "cancel_add")

        await edit_or_send(
            bot,
            user_id,
            chat_id,
            f"🔹 Добавить «{payment_type}, {item_name_clean}» ({category}, {price}₽)?",
            kb,
        )

    except Exception as e:
        logger.exception("Ошибка при обработке сообщения")
        await message.answer("⚠️ Не удалось обработать сообщение. Попробуйте ещё раз.")


# ——————— Подтверждение добавления ———————
@router.callback_query(F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    add_order(
        payment_type=data["payment_type"],
        item_name=data["item_name"],
        user_id=call.from_user.id,
        username=call.from_user.username or "",
    )

    try:
        await call.message.edit_text(
            f"✅ Заказ от {now} добавлен:\n{data['item_name']} — {data['payment_type']}"
        )
    except Exception:
        try:
            await call.message.delete()
        except:
            pass

    await state.clear()
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


# ——————— Отмена ———————
@router.callback_query(F.data == "cancel_add")
async def cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
