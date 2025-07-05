# handlers/delete.py

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
from db import (
    get_user_orders_with_items,
    delete_entire_order,
    log_action,
)
from keyboards import show_main_menu, confirm_keyboard, get_main_menu
from utils import send_and_track, notify_temp, check_membership
from config import GROUP_CHAT_ID

router = Router()
logger = logging.getLogger(__name__)

ORDERS_PER_PAGE = 5


# Показать список заказов
@router.callback_query(F.message.chat.type == "private", F.data == "delete")
async def show_orders(call: CallbackQuery, state: FSMContext):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")

    await state.clear()
    await state.update_data(offset=0)
    await display_orders(call, state, offset=0)


# Кнопка "⏭ Далее"
@router.callback_query(F.message.chat.type == "private", F.data == "next_page")
async def next_page(call: CallbackQuery, state: FSMContext):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    data = await state.get_data()
    offset = data.get("offset", 0) + ORDERS_PER_PAGE
    await state.update_data(offset=offset)
    await display_orders(call, state, offset)


# Кнопка "🔙 В начало"
@router.callback_query(F.message.chat.type == "private", F.data == "reset_page")
async def reset_page(call: CallbackQuery, state: FSMContext):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    await state.update_data(offset=0)
    await display_orders(call, state, offset=0)


async def display_orders(call: CallbackQuery, state: FSMContext, offset: int):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    """
    Показывает пагинированный список полных заказов (с позициями и суммами).
    """
    orders = get_user_orders_with_items(call.from_user.id)
    page = orders[offset : offset + ORDERS_PER_PAGE]

    if not page:
        # Показываем тост, потом просто редактируем текущее сообщение в главное меню,
        # чтобы не накладывать вторую копию
        await notify_temp(call, "🔸 У вас пока нет заказов.")
        # Импортируйте get_main_menu в начало модуля:
        # from keyboards import get_main_menu
        await call.message.edit_text(
            "Напишите заказ и тип оплаты:", reply_markup=get_main_menu()
        )
        return

    text_lines = []
    buttons = []
    for idx, order in enumerate(page, start=1):
        # форматируем время
        try:
            dt = datetime.fromisoformat(order["date"])
            formatted = dt.strftime("%Y-%m-%d %H:%M")
        except:
            formatted = order["date"]

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
        "📋 Ваши заказы:\n\n" + "\n".join(text_lines),
        reply_markup=markup,
    )


# Удалить один заказ
@router.callback_query(F.message.chat.type == "private", F.data.startswith("del_"))
async def delete_one(call: CallbackQuery, state: FSMContext):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    order_id = int(call.data.split("_", 1)[1])
    username = call.from_user.username or ""

    items = delete_entire_order(order_id, call.from_user.id, username)
    if not items:
        await call.answer("Заказ не найден или уже удалён.", show_alert=True)
        return

    try:
        await call.message.delete()
    except:
        pass

    total = sum(it["price"] * it["quantity"] for it in items)
    summary = "\n".join(
        f"- {it['item_name']} ×{it['quantity']} — {it['price']}₽" for it in items
    )
    user_text = f"❌ Заказ #{order_id} удалён:\n{summary}\n\n💰 Итого: {total}₽"

    # отправляем пользователю
    await send_and_track(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id,
        text=user_text,
    )

    # дублируем в группу
    try:
        await call.bot.send_message(
            GROUP_CHAT_ID,
            f"🗑 <b>Заказ #{order_id} удалён</b> пользователем @{call.from_user.username or call.from_user.id}\n\n"
            + summary
            + f"\n\n💰 Итого: {total}₽",
            parse_mode="HTML",
        )
        logger.info(
            f"Уведомление об удалении заказа #{order_id} отправлено в группу {GROUP_CHAT_ID}"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление об удалении в группу: {e}")

    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


# Подтверждение очистки за сегодня
@router.callback_query(F.message.chat.type == "private", F.data == "clear_today")
async def confirm_clear_today(call: CallbackQuery):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    await call.answer()
    kb = confirm_keyboard("✅ Очистить", "confirm_clear", "cancel_delete")
    await call.message.edit_text(
        "🔸 Вы действительно хотите удалить все заказы за сегодня?",
        reply_markup=kb,
    )


# Удалить за сегодня
@router.callback_query(F.message.chat.type == "private", F.data == "confirm_clear")
async def do_clear_today(call: CallbackQuery, state: FSMContext):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    await call.answer()
    today = datetime.now().date()
    orders = get_user_orders_with_items(call.from_user.id)
    deleted_count = 0

    for order in orders:
        try:
            order_date = datetime.fromisoformat(order["date"]).date()
        except:
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
        text_user = f"✅ Удалено {deleted_count} заказ(ов) за {today}"
        await send_and_track(
            bot=call.bot,
            user_id=call.from_user.id,
            chat_id=call.message.chat.id,
            text=text_user,
        )
        # дублируем в группу
        try:
            await call.bot.send_message(
                GROUP_CHAT_ID,
                f"🧹 <b>Удалено {deleted_count} заказ(ов) за {today}</b> пользователем @{call.from_user.username or call.from_user.id}",
                parse_mode="HTML",
            )
            logger.info(
                f"Уведомление об очистке за сегодня отправлено в группу {GROUP_CHAT_ID}"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление об очистке в группу: {e}")
    else:
        await notify_temp(call, f"🔸 Нет заказов за {today} для удаления.")

    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


# Отмена
@router.callback_query(F.message.chat.type == "private", F.data == "cancel_delete")
async def cancel_delete(call: CallbackQuery, state: FSMContext):
    if not await check_membership(call.bot, call.from_user.id):
        return await notify_temp(call, "⛔ Доступ запрещён: вы не участник группы.")
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
