# handlers/delete.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
from db import (
    get_user_orders_with_items,
    delete_orders_today,
    delete_entire_order,
    log_action,
)
from keyboards import show_main_menu, confirm_keyboard
from utils import send_and_track, notify_temp


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


async def display_orders(call: CallbackQuery, state: FSMContext, offset: int):
    """
    Показывает пагинированный список полных заказов (с позициями и суммами).
    """
    orders = get_user_orders_with_items(call.from_user.id)
    page = orders[offset : offset + ORDERS_PER_PAGE]

    if not page:
        # вместо edit_text — временное уведомление
        await notify_temp(call, "🔸 У вас пока нет заказов.")
        await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
        return

    text_lines = []
    buttons = []
    for idx, order in enumerate(page, start=1):
        # форматируем время
        try:
            dt = datetime.fromisoformat(order["date"])
            formatted = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            formatted = order["date"]

        # собираем позиционный список
        items_summary = "; ".join(
            f"{it['item_name']}×{it['quantity']}({it['price']}₽)"
            for it in order["items"]
        )
        text_lines.append(
            f"{idx}. {formatted} | {order['payment_type']} | {items_summary} | Итого: {order['total']}₽"
        )

        buttons.append(
            [InlineKeyboardButton(text=str(idx), callback_data=f"del_{order['id']}")]
        )

    # навигация
    nav = []
    if offset + ORDERS_PER_PAGE < len(orders):
        nav.append(InlineKeyboardButton(text="⏭ Далее", callback_data="next_page"))
    if offset > 0:
        nav.append(InlineKeyboardButton(text="🔙 В начало", callback_data="reset_page"))

    control = [
        InlineKeyboardButton(
            text="🧹 Очистить за сегодня", callback_data="clear_today"
        ),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
    ]

    markup = InlineKeyboardMarkup(inline_keyboard=buttons + [nav] + [control])
    await call.message.edit_text(
        "📋 Ваши заказы:\n\n" + "\n".join(text_lines), reply_markup=markup
    )


@router.callback_query(F.data.startswith("del_"))
async def delete_one(call: CallbackQuery, state: FSMContext):
    """
    Удаляет сразу весь заказ (orders + все его order_items),
    и показывает пользователю итоговый список позиций и сумму.
    """
    order_id = int(call.data.split("_", 1)[1])
    username = call.from_user.username or ""

    # удаляем из БД и получаем список удалённых позиций
    items = delete_entire_order(order_id, call.from_user.id, username)
    if not items:
        await call.answer("Заказ не найден или уже удалён.", show_alert=True)
        return

    # удаляем старое сообщение с кнопками
    try:
        await call.message.delete()
    except:
        pass

    # собираем summary
    total = sum(it["price"] * it["quantity"] for it in items)
    summary = "\n".join(
        f"- {it['item_name']} ×{it['quantity']} — {it['price']}₽" for it in items
    )

    await send_and_track(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text=(f"❌ Заказ #{order_id} удалён:\n{summary}\n\n💰 Итого: {total}₽"),
    )

    # показываем главное меню
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


# Очистка за сегодня
@router.callback_query(F.data == "clear_today")
async def confirm_clear_today(call: CallbackQuery):
    await call.answer()  # ACK
    kb = confirm_keyboard("✅ Очистить", "confirm_clear", "cancel_delete")
    await call.message.edit_text(
        "🔸 Вы действительно хотите удалить все заказы за сегодня?", reply_markup=kb
    )


@router.callback_query(F.data == "confirm_clear")
async def do_clear_today(call: CallbackQuery, state: FSMContext):
    await call.answer()  # ACK

    today = datetime.now().date()
    orders = get_user_orders_with_items(call.from_user.id)
    deleted_count = 0

    for order in orders:
        try:
            order_date = datetime.fromisoformat(order["date"]).date()
        except Exception:
            continue
        if order_date == today:
            items = delete_entire_order(
                order["id"], call.from_user.id, call.from_user.username or ""
            )
            if items:
                deleted_count += 1
                for it in items:
                    log_action(
                        action_type="очистка_сегодня",
                        payment_type=order["payment_type"],
                        item_name=it["item_name"],
                        user_id=call.from_user.id,
                        username=call.from_user.username or "",
                    )

    await state.clear()
    try:
        await call.message.delete()
    except:
        pass

    if deleted_count:
        # показываем полноценное подтверждение очистки
        await send_and_track(
            bot=call.bot,
            user_id=call.from_user.id,
            chat_id=call.message.chat.id,
            text=f"✅ Удалено {deleted_count} заказ(ов) за {today}",
        )
    else:
        # если нечего удалять — просто тост
        await notify_temp(call, f"🔸 Нет заказов за {today} для удаления.")

    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


# Отмена
@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
