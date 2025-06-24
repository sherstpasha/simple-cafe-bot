import json
import logging
import re

from rapidfuzz import process, fuzz
from nltk.stem.snowball import SnowballStemmer

from datetime import datetime
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from config import MENU_FILE
from states import OrderFSM
from db import add_order
from utils import edit_or_send, user_last_bot_message

router = Router()
logger = logging.getLogger(__name__)

# ——————— Загрузка меню ———————
with open(MENU_FILE, encoding="utf-8") as f:
    MENU_MAP = json.load(f)

# Инициализируем русский стеммер
stemmer = SnowballStemmer("russian")


def normalize(text: str) -> str:
    """
    Нижний регистр + удаление всего, кроме букв/цифр +
    стемминг каждого токена.
    """
    text = text.lower()
    tokens = re.findall(r"\w+", text)
    stems = [stemmer.stem(tok) for tok in tokens]
    return " ".join(stems)


# Строим маппинг нормализованной → оригинальной строки
NORMS = {}
for full_key in MENU_MAP.keys():
    norm = normalize(full_key)
    NORMS[norm] = full_key
NORM_KEYS = list(NORMS.keys())


# ——————— 1) Начало добавления — спрашиваем название ———————
@router.callback_query(F.data == "add")
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.awaiting_item_name)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_add")]
        ]
    )
    await edit_or_send(
        call.bot,
        call.from_user.id,
        call.message.chat.id,
        "🔹 Введите название напитка или десерта:",
        kb,
    )
    await call.answer()


# ——————— 2) Пользователь ввёл название — ищем ближайший пункт меню ———————
@router.message(OrderFSM.awaiting_item_name)
async def item_name_entered(message: Message, state: FSMContext):
    await message.delete()
    user_input = message.text.strip()
    user_norm = normalize(user_input)

    # Ищем лучшее совпадение
    match = process.extractOne(
        query=user_norm,
        choices=NORM_KEYS,
        scorer=fuzz.token_sort_ratio,
    )
    print(match)
    if not match or match[1] < 15:
        return await message.answer(
            "❌ Не нашёл в меню ничего похожего. "
            "Попробуйте точнее или проверьте правописание."
        )

    norm_key, score, _ = match
    full_key = NORMS[norm_key]
    category, item_name = (part.strip() for part in full_key.split(":", 1))
    price = MENU_MAP[full_key]
    logger.info(f"Matched «{full_key}» with score={score}")

    # Сохраняем в FSM
    await state.update_data(
        item_name=item_name,
        category=category,
        price=price,
    )
    await state.set_state(OrderFSM.awaiting_payment_type)

    # Спрашиваем оплату
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Наличный", callback_data="pay_cash")],
            [InlineKeyboardButton(text="Безналичный", callback_data="pay_card")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_add")],
        ]
    )
    await edit_or_send(
        message.bot,
        message.from_user.id,
        message.chat.id,
        f"🔹 Найдено: «{item_name}» ({category}), цена {price}₽ "
        f"(совпадение {int(score)}%).\nВыберите тип оплаты:",
        kb,
    )


# ——————— 3) Выбор типа оплаты ———————
@router.callback_query(
    F.data.in_(["pay_cash", "pay_card"]), F.state == OrderFSM.awaiting_payment_type
)
async def payment_type_selected(call: CallbackQuery, state: FSMContext):
    payment = "Наличный" if call.data == "pay_cash" else "Безналичный"
    await state.update_data(payment_type=payment)
    data = await state.get_data()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Добавить", callback_data="confirm_add")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")],
        ]
    )
    await edit_or_send(
        call.bot,
        call.from_user.id,
        call.message.chat.id,
        f"🔹 Добавить «{data['payment_type']}, {data['item_name']}» "
        f"({data['category']}, {data['price']}₽)?",
        kb,
    )
    await state.set_state(OrderFSM.awaiting_add_confirmation)
    await call.answer()


# ——————— 4) Подтверждение ———————
@router.callback_query(
    F.data == "confirm_add", F.state == OrderFSM.awaiting_add_confirmation
)
async def confirm_add(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    add_order(
        payment_type=data["payment_type"],
        item_name=data["item_name"],
        user_id=call.from_user.id,
        username=call.from_user.username or "",
    )
    await call.answer("✅ Запись добавлена")
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    from handlers.menu import get_main_menu

    kb = get_main_menu()
    msg = await call.message.answer("Выберите действие:", reply_markup=kb)
    user_last_bot_message[call.from_user.id] = msg.message_id


# ——————— 5) Отмена ———————
@router.callback_query(F.data == "cancel_add")
async def cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    from handlers.menu import get_main_menu

    kb = get_main_menu()
    msg = await call.message.answer("Выберите действие:", reply_markup=kb)
    user_last_bot_message[call.from_user.id] = msg.message_id
