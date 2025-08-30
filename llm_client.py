import logging
import openai
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_API_BASE_URL
import re as _re
import json as _json


logger = logging.getLogger(__name__)

openai.api_key = OPENAI_API_KEY or "dummy_key"
if OPENAI_API_BASE_URL:
    openai.api_base = OPENAI_API_BASE_URL
    openai.api_type = "openai"
    openai.api_version = None


async def complete(messages, temperature=0.2):
    """
    Универсальный запрос к одному LLM: OpenAI или локальный Ollama через OpenAI-совместимый API.
    """
    if not OPENAI_MODEL:
        raise RuntimeError("Не задана модель: установите в .env OPENAI_MODEL")
    try:
        logger.debug(f"Запрос модели {OPENAI_MODEL}: {messages!r}")
        resp = await openai.ChatCompletion.acreate(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,  # ← Добавили сюда температуру
        )
        text = resp.choices[0].message.content.strip()
        logger.debug(f"Ответ модели: {text!r}")
        return text

    except Exception:
        logger.exception("Ошибка при запросе к LLM")
        raise


class LLMParseError(RuntimeError):
    pass


def _slice_balanced_json(s: str) -> str:
    """Обрезает строку до первого сбалансированного JSON-объекта/массива. Без «умной» диагностики."""
    if not s:
        raise ValueError("Empty string for JSON slicing")
    open_ch = s[0]
    if open_ch not in "{[":
        raise ValueError("JSON must start with { or [")
    close_ch = "}" if open_ch == "{" else "]"

    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return s[: i + 1]
    raise ValueError("Unbalanced JSON in model reply")


def _extract_first_json(text: str) -> str:
    """Возвращает сырой JSON-текст из ответа (учитывает ```json ... ``` и поиск первой {/[)."""
    if not isinstance(text, str):
        raise ValueError("LLM reply is not a string")

    s = text.lstrip("\ufeff").strip()

    # fenced-блоки ```json ... ```
    m = _re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, flags=_re.IGNORECASE)
    if m:
        s = m.group(1).strip()

    if s and s[0] in "{[":
        return _slice_balanced_json(s)

    brace_pos = min([p for p in (s.find("{"), s.find("[")) if p != -1], default=-1)
    if brace_pos == -1:
        raise ValueError("JSON block not found in model reply")
    return _slice_balanced_json(s[brace_pos:])


def _extract_json_obj(text: str) -> dict:
    """Парсит JSON. Если не вышло — печатает «сломанный» JSON и пробрасывает исключение как есть."""
    raw = _extract_first_json(text)
    try:
        return _json.loads(raw)
    except Exception:
        print("---- BROKEN JSON BEGIN ----")
        try:
            print(raw)
        except Exception:
            # на случай, если там не-utf8
            print(repr(raw))
        print("---- BROKEN JSON END ----")
        raise


def _build_messages_with_exact_prompt(user_text: str, menu: dict) -> list[dict]:
    """
    ВНИМАНИЕ: это тот же промпт, только добавлены два примера с корицей.
    """
    MAIN_MENU = menu["main"]
    ADDONS = menu["addons"]
    main_text = "\n".join(f"- {k}" for k in MAIN_MENU)
    addon_text = "\n".join(f"- {k}" for k in ADDONS)

    system_instructions = (
        "Ты — помощник для разбора заказа из текста.\n\n"
        "Вот актуальное меню с ценами:\n"
        "Основные позиции:\n" + main_text + "\n\nДобавки:\n" + addon_text + "\n\n"
        "Твоя задача:\n"
        '– Определи список заказанных позиций (it), основываясь **только** на "Основных позициях".\n'
        "– К каждой позиции укажи:\n"
        "  • n — item_name строго из основного меню\n"
        "  • q — quantity (целое, default=1)\n"
        "  • a — список addons (имя и цена из ADDONS, иначе price=0)\n"
        "– Определи pay:\n"
        "  • 1 — Безналичный\n"
        "  • 0 — Наличный\n"
        "  • -1 — не указано\n\n"
        "**Важно**:\n"
        '– В n только точное совпадение из "Основных позиций".\n'
        "– В a только названия из раздела добавок или новые (free).\n\n"
        "Формат ответа — только JSON-объект с:\n"
        '- "it": [...]\n'
        '- "pay": number\n\n'
        "Примеры:\n\n"
        '- Запрос: "2 американо наличкой"\n'
        "{\n"
        '  "it":[\n'
        '    {"n":"Американо","q":2,"a":[]}\n'
        "  ],\n"
        '  "pay":0\n'
        "}\n\n"
        '- Запрос: "латте с соленой карамелью и капучино с фисташковым сиропом на карту"\n'
        "{\n"
        '  "it":[\n'
        '    {"n":"Латте","q":1,"a":["Солёная карамель (добавка)"]},\n'
        '    {"n":"Капучино","q":1,"a":["Фисташковый сироп"]}\n'
        "  ],\n"
        '  "pay":1\n'
        "}\n\n"
        '- Запрос: "чай с грушей ромашковый и ройбуш на кокосовом молоке перевод"\n'
        "{\n"
        '  "it":[\n'
        '    {"n":"Чай: Ромашковый с грушей","q":1,"a":[]},\n'
        '    {"n":"Чай: Ройбуш Самурай","q":1,"a":["Альтернативное молоко (миндаль/кокос)"]}\n'
        "  ],\n"
        '  "pay":1\n'
        "}\n\n"
        '- Запрос: "макарон, чизкейк и какао с карамелью нал"\n'
        "{\n"
        '  "it":[\n'
        '    {"n":"Десерты: Макарон","q":1,"a":[]},\n'
        '    {"n":"Десерты: Чизкейк","q":1,"a":[]},\n'
        '    {"n":"Какао: Классический","q":1,"a":["Карамельный сироп"]}\n'
        "  ],\n"
        '  "pay":0\n'
        "}\n\n"
        # --- ДОБАВЛЕННЫЕ ПРИМЕРЫ ПРО КОРИЦУ ---
        '- Запрос: "капучино с корицей наличка"\n'
        "{\n"
        '  "it":[\n'
        '    {"n":"Капучино","q":1,"a":["Корица"]}\n'
        "  ],\n"
        '  "pay":0\n'
        "}\n\n"
        '- Запрос: "капучино с сахаром и корицей перевод"\n'
        "{\n"
        '  "it":[\n'
        '    {"n":"Капучино","q":1,"a":["Сахар","Корица"]}\n'
        "  ],\n"
        '  "pay":1\n'
        "}\n\n"
        '- Запрос: "капучино с соленой карамелью без наличка"\n'
        "{\n"
        '  "it":[\n'
        '    {"n":"Капучино Солёная карамель","q":1,"a":[]}\n'
        "  ],\n"
        '  "pay":1\n'
        "}\n\n"
        # --- КОНЕЦ ДОБАВЛЕННЫХ ПРИМЕРОВ ---
        "Никакого другого текста — только JSON."
    )

    return [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_text},
    ]


_LATIN_TO_CYR = {
    "A": "А",
    "a": "а",
    "B": "В",  # только верхний регистр безопасно
    "E": "Е",
    "e": "е",
    "K": "К",
    "k": "к",
    "M": "М",
    "m": "м",
    "H": "Н",  # верхний регистр; нижний 'h' не трогаем
    "O": "О",
    "o": "о",
    "P": "Р",
    "p": "р",
    "C": "С",
    "c": "с",
    "T": "Т",
    "t": "т",
    "X": "Х",
    "x": "х",
    "Y": "У",
    "y": "у",
}


def _normalize_homoglyphs_value(s: str) -> str:
    """Заменяет латинские символы-двойники на кириллицу в одной строке."""
    return "".join(_LATIN_TO_CYR.get(ch, ch) for ch in s)


def _normalize_values_only(obj):
    """
    Рекурсивно проходит по структуре и нормализует ТОЛЬКО значения-строки.
    Ключи словарей не меняем.
    """
    if isinstance(obj, dict):
        return {k: _normalize_values_only(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_values_only(v) for v in obj]
    if isinstance(obj, str):
        return _normalize_homoglyphs_value(obj)
    return obj


async def parse_order_from_text(
    user_text: str, menu: dict, *, temperature: float = 0.0
) -> dict:
    """Собирает тот же промпт, шлёт в модель и парсит JSON. Ошибки парсинга — обычные исключения."""
    messages = _build_messages_with_exact_prompt(user_text, menu)
    logger.debug(messages)
    reply = await complete(messages, temperature=temperature)
    logger.info(f"[LLM reply]: {reply}")

    # Парсим и нормализуем латиницу в значениях
    result = _extract_json_obj(reply)
    result = _normalize_values_only(result)  # ← ВАЖНО: нормализация значений

    raw_items = result.get("it", [])
    try:
        pay_code = int(result.get("pay", -1))
        if pay_code not in (-1, 0, 1):
            pay_code = -1
    except Exception:
        pay_code = -1
    return {"it": raw_items, "pay": pay_code}
