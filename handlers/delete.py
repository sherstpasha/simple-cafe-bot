# handlers/delete.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
from db import get_user_orders, delete_order, log_action, delete_orders_today
from keyboards import show_main_menu, confirm_keyboard
from utils import send_and_track


router = Router()

ORDERS_PER_PAGE = 5


# Показать список заказов
@router.callback_query(F.data == "delete")
async def show_orders(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(offset=0)
    await display_orders(call, state, offset=0)


# Кнопка "⏭ Далее"
@router.callback_query(F.data == "next_page")
async def next_page(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offset = data.get("offset", 0) + ORDERS_PER_PAGE
    await state.update_data(offset=offset)
    await display_orders(call, state, offset)


# Кнопка "🔙 В начало"
@router.callback_query(F.data == "reset_page")
async def reset_page(call: CallbackQuery, state: FSMContext):
    await state.update_data(offset=0)
    await display_orders(call, state, offset=0)


# Отображение заказов
async def display_orders(call: CallbackQuery, state: FSMContext, offset: int):
    orders = get_user_orders(call.from_user.id)
    page = orders[offset : offset + ORDERS_PER_PAGE]

    if not page:
        await call.message.edit_text("🔸 У вас пока нет заказов.")
        await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
        return

    text_lines = []
    buttons = []
    for idx, order in enumerate(page, start=1):
        try:
            dt = datetime.fromisoformat(order["date"])
            formatted = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            formatted = order["date"]

        text_lines.append(
            f"{idx}. {formatted} | {order['payment_type']} | {order['item_name']}"
        )
        # Кнопка удаления по ID заказа
        buttons.append(
            [InlineKeyboardButton(text=str(idx), callback_data=f"del_{order['id']}")]
        )

    # Навигация
    navigation = []
    if offset + ORDERS_PER_PAGE < len(orders):
        navigation.append(
            InlineKeyboardButton(text="⏭ Далее", callback_data="next_page")
        )
    if offset > 0:
        navigation.append(
            InlineKeyboardButton(text="🔙 В начало", callback_data="reset_page")
        )

    # Управляющие кнопки
    control = [
        InlineKeyboardButton(
            text="🧹 Очистить за сегодня", callback_data="clear_today"
        ),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
    ]

    markup = InlineKeyboardMarkup(inline_keyboard=buttons + [navigation] + [control])
    await call.message.edit_text(
        "📋 Ваши заказы:\n\n" + "\n".join(text_lines), reply_markup=markup
    )


# Удаление одной записи
@router.callback_query(F.data.startswith("del_"))
async def delete_one(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[1])

    # Получаем данные заказа по ID
    orders = get_user_orders(call.from_user.id)
    order = next((o for o in orders if o["id"] == order_id), None)

    if order is None:
        await call.answer("Запись не найдена.", show_alert=True)
        return

    # Удаляем из БД
    delete_order(order_id, call.from_user.id)

    # Логируем
    log_action(
        action_type="delete",
        payment_type=order["payment_type"],
        item_name=order["item_name"],
        user_id=call.from_user.id,
        username=call.from_user.username or "",
    )

    # Удаляем старое сообщение с кнопками (если ещё висит)
    try:
        await call.message.delete()
    except Exception:
        pass

    # Отправляем подтверждение
    from utils import send_and_track

    try:
        dt = datetime.fromisoformat(order["date"])
        formatted = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        formatted = order["date"]

    await send_and_track(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text=f"❌ Запись от: {formatted}, {order['payment_type']}, {order['item_name']} удалена.",
    )


# Очистка за сегодня
@router.callback_query(F.data == "clear_today")
async def confirm_clear_today(call: CallbackQuery):
    markup = confirm_keyboard("✅ Очистить", "confirm_clear", "cancel_delete")
    await call.message.edit_text(
        "🔸 Очистить все записи за сегодня?", reply_markup=markup
    )


@router.callback_query(F.data == "confirm_clear")
async def do_clear_today(call: CallbackQuery, state: FSMContext):
    count, deleted_orders = delete_orders_today(call.from_user.id)
    for order in deleted_orders:
        log_action(
            "очистка_сегодня",
            order["payment_type"],
            order["item_name"],
            call.from_user.id,
            call.from_user.username or "",
        )

    await state.clear()

    # Удалить предыдущее сообщение с кнопками
    try:
        await call.message.delete()
    except Exception:
        pass

    # Отправить подтверждение
    await send_and_track(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text=f"✅ Очищено {count} записи(ей) за {datetime.now().date()}",
    )

    # Показать главное меню
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


# Отмена
@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
