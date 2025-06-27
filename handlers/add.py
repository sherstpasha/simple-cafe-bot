# handlers/add.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import json, logging, re, ast, sqlite3, asyncio

from mistralai import Mistral
from config import MENU_FILE, MISTRAL_API_KEY, MISTRAL_MODEL
from utils import edit_or_send, transcribe_voice, notify_temp, send_and_track
from keyboards import show_main_menu, confirm_keyboard
from db import add_order_items

router = Router()
logger = logging.getLogger(__name__)

# загружаем меню из JSON
with open(MENU_FILE, encoding="utf-8") as f:
    MENU_MAP = json.load(f)

mistral_client = Mistral(api_key=MISTRAL_API_KEY)


@router.message()
async def handle_message(message: Message, state: FSMContext, bot):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        # удаляем исходное сообщение
        try:
            await message.delete()
        except:
            pass

        # получаем текст (или распознаём голос)
        if message.voice:
            user_text = await transcribe_voice(bot, message)
            if not user_text:
                return await notify_temp(
                    message, "🗣 Не удалось распознать речь, попробуйте ещё раз."
                )
        else:
            user_text = message.text.strip()

        logger.info(f"[User Input]: {user_text}")

        # готовим меню в текст для промпта
        menu_text = "\n".join(f"- {k}" for k in MENU_MAP.keys())

        # промпт для LLM
        response = mistral_client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помогаешь принимать заказы в кафе.\n"
                        "Вот актуальное меню:\n"
                        f"{menu_text}\n\n"
                        "В сообщении пользователя есть основные позиции (напитки/товары) и опциональные добавки.\n"
                        "Основные позиции (item_name) **обязательно** должны быть из меню.\n"
                        "Добавки (addons) могут быть любыми: если совпадают с пунктом меню — их цена берётся из меню, "
                        "если нет — считаются бесплатными (0₽).\n\n"
                        "Оплата всегда только двух видов: **Наличный** или **Безналичный**.\n"
                        "Если в тексте есть «картой», «карта», «перевод» и т.п. — выбери **Безналичный**; "
                        "если «наличными», «наличка» и т.п. — **Наличный**. Если оплата не написана не пиши ничего.\n\n"
                        "В ответе СТРОГО сначала JSON-массив позиций с полями:\n"
                        "  • item_name: строка\n"
                        "  • quantity: число\n"
                        "  • addons: массив строк (может быть пустым)\n\n"
                        "А затем на отдельной строке — payment_type: <Наличный или Безналичный>.\n\n"
                        "Пример:\n"
                        "```\n"
                        "[\n"
                        '  {"item_name": "Латте", "quantity": 1, "addons": ["Сахар"]},\n'
                        '  {"item_name": "Американо", "quantity": 2, "addons": []}\n'
                        "]\n"
                        "payment_type: Наличный\n"
                        "```"
                    ),
                },
                {"role": "user", "content": user_text},
            ],
        )

        reply = response.choices[0].message.content.strip()
        logger.info(f"[LLM reply]: {reply}")

        # парсим payment_type
        m = re.search(r"payment_type:\s*(\w+)", reply, re.IGNORECASE)
        payment_type = m.group(1).capitalize() if m else ""
        if payment_type not in ("Наличный", "Безналичный"):
            return await notify_temp(
                message, "⚠️ Тип оплаты не распознан. Укажите «наличными» или «картой»."
            )

        # парсим JSON-блок
        block = re.search(r"\[.*\]", reply, re.DOTALL)
        raw_items = ast.literal_eval(block.group(0)) if block else []
        if not raw_items:
            return await notify_temp(
                message, "⚠️ Не удалось распознать ни одной позиции заказа."
            )

        # нормализуем
        normalized = []
        for entry in raw_items:
            base = entry.get("item_name", "").strip()
            qty = int(entry.get("quantity", 1))
            addons = entry.get("addons", [])
            # базовая позиция
            key = next((k for k in MENU_MAP if base.lower() in k.lower()), None)
            if not key:
                continue
            price = MENU_MAP[key]
            name = key.split(":", 1)[-1].strip()

            # обработка add-ons
            addons_info = []
            for a in addons:
                ak = next((k for k in MENU_MAP if a.lower() in k.lower()), None)
                ap = MENU_MAP[ak] if ak else 0
                an = ak.split(":", 1)[-1].strip() if ak else a
                addons_info.append({"name": an, "price": ap})

            for _ in range(qty):
                normalized.append(
                    {
                        "item_name": name,
                        "payment_type": payment_type,
                        "price": price,
                        "quantity": 1,
                        "addons": addons_info,
                    }
                )

        if not normalized:
            return await notify_temp(message, "⚠️ Ни одна из позиций не нашлась в меню.")

        # сохраняем в state и ждём подтверждения
        await state.update_data(items=normalized)
        await state.set_state("awaiting_add_confirmation")

        # собираем summary
        total = sum(
            it["price"] + sum(a["price"] for a in it["addons"]) for it in normalized
        )
        lines = []
        for i, it in enumerate(normalized, start=1):
            lines.append(f"{i}) {it['item_name']} — {it['price']}₽")
            for a in it["addons"]:
                lines.append(f"   • {a['name']} — {a['price']}₽")

        kb = confirm_keyboard("✅ Добавить", "confirm_add", "cancel_add")
        await edit_or_send(
            bot,
            user_id,
            chat_id,
            f"🔹 Подтвердите заказ (оплата: <b>{payment_type}</b>):\n"
            + "\n".join(lines)
            + f"\n\n💰 Итого: <b>{total}₽</b>",
            kb,
        )

    except Exception as e:
        logger.exception("Ошибка при обработке сообщения")
        await notify_temp(message, "⚠️ Не удалось обработать заказ. Попробуйте ещё раз.")


@router.callback_query(F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    items = data.get("items", [])
    if not items:
        return await notify_temp(call, "⚠️ Нет ни одной позиции для добавления.")

    # повторяем до 3-х раз, если БД заблокирована
    for _ in range(3):
        try:
            add_order_items(items, call.from_user.id, call.from_user.username or "")
            break
        except sqlite3.OperationalError as err:
            if "locked" in str(err).lower():
                await asyncio.sleep(0.5)
                continue
            else:
                return await notify_temp(
                    call, "⚠️ Ошибка базы данных. Попробуйте позже."
                )
    else:
        return await notify_temp(
            call, "⚠️ Не удалось записать заказ. Попробуйте ещё раз."
        )

    # удаляем клавиатуру
    try:
        await call.message.delete()
    except:
        pass

    # финальный ответ
    total = sum(it["price"] + sum(a["price"] for a in it["addons"]) for it in items)
    lines = []
    for i, it in enumerate(items, start=1):
        lines.append(f"{i}) {it['item_name']} — {it['price']}₽")
        for a in it["addons"]:
            lines.append(f"   • {a['name']} — {a['price']}₽")

    await send_and_track(
        call.bot,
        call.from_user.id,
        call.message.chat.id,
        "✅ Заказ добавлен (оплата: <b>{}</b>):\n".format(items[0]["payment_type"])
        + "\n".join(lines)
        + f"\n\n💰 Итого: <b>{total}₽</b>",
    )

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
