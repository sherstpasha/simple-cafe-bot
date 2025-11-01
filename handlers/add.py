from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import json, logging, sqlite3, asyncio

from config import MENU_FILE, GROUP_CHAT_ID
from llm_client import parse_order_from_text, LLMParseError
from utils import (
    edit_or_send,
    transcribe_voice,
    notify_temp,
    send_and_track,
    check_membership,
)
from keyboards import show_main_menu, confirm_keyboard
from db import add_order_items

router = Router()
logger = logging.getLogger(__name__)

with open(MENU_FILE, encoding="utf-8") as f:
    MENU = json.load(f)
MAIN_MENU = MENU["main"]
ADDONS = MENU["addons"]


@router.message(F.chat.type == "private", F.voice)
@router.message(F.chat.type == "private", F.text & ~F.text.startswith("/"))
async def handle_message(message: Message, state: FSMContext, bot):

    user_id = message.from_user.id
    if not await check_membership(bot, user_id):
        return await notify_temp(message, "⛔ Доступ запрещён: вы не участник группы.")

    await state.clear()
    
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        try:
            await message.delete()
        except:
            pass
        if message.voice:
            user_text = await transcribe_voice(bot, message)
            if not user_text:
                return await notify_temp(
                    message, "🗣 Не получилось распознать речь, попробуйте ещё раз."
                )
        else:
            user_text = (message.text or "").strip()

        if not user_text:
            return await notify_temp(message, "⚠️ Пустой запрос.")

        logger.info(f"[User Input]: {user_text}")

        try:
            parsed = await parse_order_from_text(user_text, MENU, temperature=0.2)
        except LLMParseError:
            logger.exception("Failed to parse model JSON")
            return await notify_temp(message, "⚠️ Не удалось распознать ответ модели.")
        except Exception:
            logger.exception("LLM call failed")
            return await notify_temp(message, "⚠️ Ошибка при обращении к модели.")

        raw_items = parsed.get("it", [])
        pay_code = parsed.get("pay", -1)

        await state.update_data(raw_text=user_text)
        if pay_code == 0:
            pay_text = "Наличный"
        elif pay_code == 1:
            pay_text = "Безналичный"
        else:
            pay_text = "Не указано"

        normalized = []
        for entry in raw_items:
            name = (entry.get("n") or entry.get("name") or "").strip()
            if name not in MAIN_MENU:
                logger.warning(f"Пропущено: '{name}'")
                continue

            try:
                qty = int(entry.get("q", 1))
            except Exception:
                qty = 1
            qty = max(1, qty)

            addons_raw = entry.get("a", [])
            addons_info = []
            for addon in addons_raw:
                ad = str(addon).strip()
                if not ad:
                    continue
                addons_info.append({"name": ad, "price": ADDONS.get(ad, 0)})

            price = MAIN_MENU[name]
            for _ in range(qty):
                normalized.append(
                    {
                        "item_name": name,
                        "quantity": 1,
                        "price": price,
                        "addons": addons_info,
                        "payment_type": pay_text,
                    }
                )

        if not normalized:
            return await notify_temp(message, "⚠️ Ни одна позиция не найдена в меню.")

        await state.update_data(items=normalized)
        await state.set_state("awaiting_add_confirmation")

        total = sum(
            it["price"] + sum(a["price"] for a in it["addons"]) for it in normalized
        )
        lines = []
        for i, it in enumerate(normalized, 1):
            lines.append(f"{i}) {it['item_name']} — {it['price']}₽")
            for a in it["addons"]:
                lines.append(f"   • {a['name']} — {a['price']}₽")

        kb = confirm_keyboard("✅ Добавить", "confirm_add", "cancel_add")
        prompt = (
            f"🔹 Подтвердите заказ (оплата: <b>{pay_text}</b>)\n\n"
            f"Запрос: <i>{user_text}</i>\n\n"
            + "\n".join(lines)
            + f"\n\n💰 Итого: <b>{total}₽</b>"
        )
        await edit_or_send(
            bot,
            user_id,
            chat_id,
            prompt,
            kb,
        )
    except Exception:
        logger.exception("Ошибка при обработке сообщения")
        await notify_temp(message, "⚠️ Не удалось обработать заказ.")


async def _process_order_confirmation(call: CallbackQuery, state: FSMContext, is_staff_order: bool = False):
    """Общая функция для обработки подтверждения заказа (обычного или для сотрудника)"""
    try:
        data = await state.get_data()
        items = data.get("items", [])
        raw_text = data.get("raw_text", "")
        
        if not raw_text:
            logger.warning(f"Empty raw_text for user {call.from_user.id}")
            raw_text = "[текст заказа не сохранен]"

        if not items:
            logger.warning(f"User {call.from_user.id} tried to confirm order with no items")
            return await notify_temp(call, "⚠️ Нет ни одной позиции.")

        # Попытка сохранить заказ в БД с повторами
        order_id = None
        last_error = None
        for attempt in range(3):
            try:
                order_id = add_order_items(
                    items,
                    call.from_user.id,
                    call.from_user.username or "",
                    raw_text,
                    is_staff=is_staff_order,
                )
                logger.info(f"Order #{order_id} saved successfully for user {call.from_user.id} (attempt {attempt + 1})")
                break
            except sqlite3.OperationalError as err:
                last_error = err
                if "locked" in str(err).lower():
                    logger.warning(f"Database locked, attempt {attempt + 1}/3 for user {call.from_user.id}")
                    await asyncio.sleep(0.5)
                    continue
                logger.error(f"Database error while saving order for user {call.from_user.id}: {err}")
                return await notify_temp(call, "⚠️ Ошибка базы данных. Попробуйте позже.")
            except Exception as err:
                last_error = err
                logger.exception(f"Unexpected error while saving order for user {call.from_user.id}")
                return await notify_temp(call, "⚠️ Не удалось сохранить заказ. Попробуйте позже.")

        # Проверяем, что заказ действительно сохранился
        if order_id is None:
            logger.error(f"Failed to save order for user {call.from_user.id} after 3 attempts. Last error: {last_error}")
            return await notify_temp(call, "⚠️ Не удалось сохранить заказ после нескольких попыток. Попробуйте позже.")

        # Удаляем предыдущее сообщение
        try:
            await call.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message for user {call.from_user.id}: {e}")

        # Формируем текст подтверждения
        total = sum(it["price"] + sum(a["price"] for a in it["addons"]) for it in items)
        lines = []
        for i, it in enumerate(items, 1):
            staff_suffix = " (для сотрудника)" if is_staff_order else ""
            lines.append(f"{i}) {it['item_name']} — {it['price']}₽{staff_suffix}")
            for a in it["addons"]:
                lines.append(f"   • {a['name']} — {a['price']}₽")

        confirmation = (
            f"✅ Заказ #{order_id} добавлен (оплата: <b>{items[0]['payment_type']}</b>)\n"
            + ("👥 Заказ помечен как для сотрудника.\n" if is_staff_order else "")
            + "\n"
            + f"Запрос: <i>{raw_text}</i>\n\n"
            + "\n".join(lines)
            + f"\n\n💰 Итого: <b>{total}₽</b>"
        )

        # Отправляем подтверждение пользователю
        try:
            await send_and_track(
                call.bot,
                call.from_user.id,
                call.message.chat.id,
                confirmation,
            )
            logger.info(f"Confirmation message sent to user {call.from_user.id} for order #{order_id}")
        except Exception as e:
            logger.error(f"Failed to send confirmation to user {call.from_user.id} for order #{order_id}: {e}")
            # Пытаемся отправить хотя бы простое уведомление
            try:
                await call.bot.send_message(
                    call.message.chat.id,
                    f"✅ Заказ #{order_id} сохранён (но возникла ошибка при отображении деталей)",
                    parse_mode="HTML",
                )
            except Exception as e2:
                logger.error(f"Failed to send fallback message to user {call.from_user.id}: {e2}")
                # Уведомление в группу всё равно попытаемся отправить

        # Отправляем уведомление в группу
        if not GROUP_CHAT_ID:
            logger.warning(f"GROUP_CHAT_ID is not configured - skipping group notification for order #{order_id}")
        else:
            try:
                staff_prefix = "👥 [ДЛЯ СОТРУДНИКА] " if is_staff_order else ""
                await call.bot.send_message(
                    GROUP_CHAT_ID,
                    f"📣 <b>{staff_prefix}Новый заказ от @{call.from_user.username or call.from_user.id}</b>\n\n"
                    + confirmation,
                    parse_mode="HTML",
                )
                logger.info(f"Notification sent to group {GROUP_CHAT_ID} for order #{order_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to group {GROUP_CHAT_ID} for order #{order_id}: {e}")

        # Очищаем состояние и показываем главное меню
        await state.clear()
        try:
            await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
        except Exception as e:
            logger.error(f"Failed to show main menu to user {call.from_user.id}: {e}")

    except Exception as e:
        logger.exception(f"Critical error in _process_order_confirmation for user {call.from_user.id}")
        try:
            await notify_temp(call, "⚠️ Произошла критическая ошибка. Пожалуйста, попробуйте снова.")
        except:
            pass
        try:
            await state.clear()
        except:
            pass


@router.callback_query(F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _process_order_confirmation(call, state, is_staff_order=False)


@router.callback_query(F.data == "confirm_add_staff")
async def confirm_add_staff(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _process_order_confirmation(call, state, is_staff_order=True)


@router.callback_query(F.data == "cancel_add")
async def cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
