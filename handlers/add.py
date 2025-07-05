from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import json, logging, sqlite3, asyncio

from config import MENU_FILE
from llm_client import complete
from utils import edit_or_send, transcribe_voice, notify_temp, send_and_track
from keyboards import show_main_menu, confirm_keyboard
from db import add_order_items

router = Router()
logger = logging.getLogger(__name__)

# загружаем меню из JSON
with open(MENU_FILE, encoding="utf-8") as f:
    MENU = json.load(f)
MAIN_MENU = MENU["main"]
ADDONS = MENU["addons"]


@router.message()
async def handle_message(message: Message, state: FSMContext, bot):
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
            user_text = message.text.strip()
        logger.info(f"[User Input]: {user_text}")

        # готовим меню для промпта
        main_text = "\n".join(f"- {k}" for k in MAIN_MENU)
        addon_text = "\n".join(f"- {k}" for k in ADDONS)

        system_instructions = f"""
Ты — помощник для разбора заказа из текста.

Вот актуальное меню с ценами:
Основные позиции:
{main_text}

Добавки:
{addon_text}

Твоя задача:
– Определи список заказанных позиций (it), основываясь **только** на "Основных позициях".
– К каждой позиции укажи:
  • n — item_name строго из основного меню
  • q — quantity (целое, default=1)
  • a — список addons (имя и цена из ADDONS, иначе price=0)
– Определи pay:
  • 1 — Безналичный
  • 0 — Наличный
  • -1 — не указано

**Важно**:
– В n только точное совпадение из "Основных позиций".
– В a только названия из раздела добавок или новые (free).

Формат ответа — только JSON-объект с:
- "it": [...]
- "pay": number

Примеры:

- Запрос: "2 американо наличкой"
{{
  "it":[
    {{"n":"Американо","q":2,"a":[]}}
  ],
  "pay":0
}}

- Запрос: "латте с шоколадным сиропом и капучино с фисташковым сиропом на карту"
{{
  "it":[
    {{"n":"Латте","q":1,"a":["Шоколадный сироп"]}},
    {{"n":"Капучино","q":1,"a":["Фисташковый сироп"]}}
  ],
  "pay":1
}}

- Запрос: "чай с грушей ромашковый и ройбуш на кокосовом молоке перевод"
{{
  "it":[
    {{"n":"Чай: Ромашковый с грушей","q":1,"a":[]}},
    {{"n":"Чай: Ройбуш Самурай","q":1,"a":["Альтернативное молоко (миндаль/кокос)"]}}
  ],
  "pay":1
}}

Никакого другого текста — только JSON.
""".strip()

        prompt_messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_text},
        ]
        logger.debug(prompt_messages)

        reply = await complete(prompt_messages)
        logger.info(f"[LLM reply]: {reply}")

        # парсим ответ
        try:
            result = json.loads(reply)
            raw_items = result.get("it", [])
            pay_code = int(result.get("pay", -1))
        except json.JSONDecodeError:
            return await notify_temp(message, "⚠️ Не удалось распознать ответ модели.")

        # сопоставление pay
        pay_text = ""
        if pay_code == 0:
            pay_text = "Наличный"
        elif pay_code == 1:
            pay_text = "Безналичный"

        # нормализация
        normalized = []
        for entry in raw_items:
            name = entry.get("n", "").strip()
            if name not in MAIN_MENU:
                logger.warning(f"Пропущено: '{name}'")
                continue
            qty = int(entry.get("q", 1))
            addons_raw = entry.get("a", [])
            addons_info = []
            for addon in addons_raw:
                ad = addon.strip()
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
        await edit_or_send(
            bot,
            user_id,
            chat_id,
            f"🔹 Подтвердите заказ (оплата: <b>{pay_text or 'не указана'}</b>):\n"
            + "\n".join(lines)
            + f"\n\n💰 Итого: <b>{total}₽</b>",
            kb,
        )
    except Exception as e:
        logger.exception("Ошибка при обработке сообщения")
        await notify_temp(message, "⚠️ Не удалось обработать заказ.")


@router.callback_query(F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    items = data.get("items", [])
    if not items:
        return await notify_temp(call, "⚠️ Нет ни одной позиции.")
    for _ in range(3):
        try:
            add_order_items(items, call.from_user.id, call.from_user.username or "")
            break
        except sqlite3.OperationalError as err:
            if "locked" in str(err).lower():
                await asyncio.sleep(0.5)
                continue
            return await notify_temp(call, "⚠️ Ошибка базы данных.")
    try:
        await call.message.delete()
    except:
        pass
    total = sum(it["price"] + sum(a["price"] for a in it["addons"]) for it in items)
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}) {it['item_name']} — {it['price']}₽")
        for a in it["addons"]:
            lines.append(f"   • {a['name']} — {a['price']}₽")
    await send_and_track(
        call.bot,
        call.from_user.id,
        call.message.chat.id,
        f"✅ Заказ добавлен (оплата: <b>{items[0]['payment_type']}</b>):\n"
        + "\n".join(lines)
        + f"\n\n💰 Итого: <b>{total}₽</b>",
    )
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
