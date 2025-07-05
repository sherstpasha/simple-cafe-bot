import logging
import openai
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_API_BASE_URL

logger = logging.getLogger(__name__)

# Настраиваем клиент
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
