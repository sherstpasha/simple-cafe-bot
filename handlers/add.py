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

# загружаем меню из JSON
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

    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        # удаляем оригинал
        try:
            await message.delete()
        except:
            pass

        # получаем текст или распознаём голос
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

        # сохраняем исходный текст для БД и подтверждения
        await state.update_data(raw_text=user_text)
        logger.info(f"[User Input]: {user_text}")

        # === единый вызов в llm_client: промпт лежит там ===
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

        # сопоставление pay
        if pay_code == 0:
            pay_text = "Наличный"
        elif pay_code == 1:
            pay_text = "Безналичный"
        else:
            pay_text = "Не указано"

        # нормализация
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
            # текущая логика — «размножаем» по количеству (quantity=1 в каждой строке)
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
        # Формируем текст подтверждения с исходным запросом сверху
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


@router.callback_query(F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext):
    await call.answer()

    data = await state.get_data()
    items = data.get("items", [])
    raw_text = data.get("raw_text", "")

    if not items:
        return await notify_temp(call, "⚠️ Нет ни одной позиции.")

    # сохраняем заказ вместе с исходным текстом
    for _ in range(3):
        try:
            add_order_items(
                items,
                call.from_user.id,
                call.from_user.username or "",
                raw_text,
            )
            break
        except sqlite3.OperationalError as err:
            if "locked" in str(err).lower():
                await asyncio.sleep(0.5)
                continue
            return await notify_temp(call, "⚠️ Ошибка базы данных.")

    # удаляем сообщение с кнопками подтверждения
    try:
        await call.message.delete()
    except:
        pass

    # подготавливаем текст подтверждения
    total = sum(it["price"] + sum(a["price"] for a in it["addons"]) for it in items)
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}) {it['item_name']} — {it['price']}₽")
        for a in it["addons"]:
            lines.append(f"   • {a['name']} — {a['price']}₽")

    confirmation = (
        f"✅ Заказ добавлен (оплата: <b>{items[0]['payment_type']}</b>)\n\n"
        f"Запрос: <i>{raw_text}</i>\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Итого: <b>{total}₽</b>"
    )

    # 1) отправляем пользователю
    await send_and_track(
        call.bot,
        call.from_user.id,
        call.message.chat.id,
        confirmation,
    )

    # 2) дублируем уведомление в группу
    try:
        await call.bot.send_message(
            GROUP_CHAT_ID,
            f"📣 <b>Новый заказ от @{call.from_user.username or call.from_user.id}</b>\n\n"
            + confirmation,
            parse_mode="HTML",
        )
        logger.info(f"Уведомление о новом заказе отправлено в группу {GROUP_CHAT_ID}")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление в группу {GROUP_CHAT_ID}: {e}")

    # очищаем состояние и возвращаем главное меню
    await state.clear()
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)


@router.callback_query(F.data == "cancel_add")
async def cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    await show_main_menu(call.from_user.id, call.message.chat.id, call.bot)
