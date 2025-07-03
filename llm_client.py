# llm_client.py

import logging
import itertools
import openai
from mistralai import Mistral
from config import (
    PROVIDER,
    OPENAI_API_KEYS,
    OPENAI_MODELS,
    OPENAI_API_BASE_URLS,
    MISTRAL_API_KEYS,
    MISTRAL_MODELS,
    MISTRAL_API_BASE_URLS,
)

logger = logging.getLogger(__name__)

# Prepare cyclic iterators for keys, models, and base URLs
openai_key_iter = itertools.cycle(OPENAI_API_KEYS)
openai_model_iter = itertools.cycle(OPENAI_MODELS) if OPENAI_MODELS else itertools.repeat(None)
openai_url_iter = itertools.cycle(OPENAI_API_BASE_URLS) if OPENAI_API_BASE_URLS else None

mistral_key_iter = itertools.cycle(MISTRAL_API_KEYS)
mistral_model_iter = itertools.cycle(MISTRAL_MODELS) if MISTRAL_MODELS else itertools.repeat(None)
mistral_url_iter = itertools.cycle(MISTRAL_API_BASE_URLS) if MISTRAL_API_BASE_URLS else None

async def complete(messages, primary_provider=None):
    """
    Универсальная обёртка для chat-completion с fallback между провайдерами, моделями и endpoint'ами.

    :param messages: список dict для модели
    :param primary_provider: 'openai' или 'mistral'; если None, берётся из PROVIDER
    :return: строка с ответом
    :raises RuntimeError: если все провайдеры и URL не вернули ответ
    """
    first = (primary_provider or PROVIDER).lower()
    order = [first] + [p for p in ("openai", "mistral") if p != first]
    last_error = None

    for prov in order:
        try:
            if prov == "openai":
                # Rotate API key, model, and base URL
                key = next(openai_key_iter)
                openai.api_key = key
                model = next(openai_model_iter)
                logger.debug(f"Using OpenAI key: {key[:8]}..., model: {model}")
                if openai_url_iter:
                    url = next(openai_url_iter)
                    openai.api_base = url
                    logger.debug(f"Using OpenAI base URL: {url}")
                # Call OpenAI
                resp = await openai.ChatCompletion.acreate(
                    model=model,
                    messages=messages
                )
                return resp.choices[0].message.content.strip()

            elif prov == "mistral":
                # Rotate API key, model, and base URL
                key = next(mistral_key_iter)
                model = next(mistral_model_iter)
                kwargs = {"api_key": key}
                if mistral_url_iter:
                    base = next(mistral_url_iter)
                    kwargs["base_url"] = base
                    logger.debug(f"Using Mistral base URL: {base}")
                logger.debug(f"Using Mistral key: {key[:8]}..., model: {model}")
                client = Mistral(**kwargs)
                resp = client.chat.complete(
                    model=model,
                    messages=messages
                )
                return resp.choices[0].message.content.strip()

        except Exception as e:
            logger.warning(f"Provider '{prov}' attempt failed: {e}")
            last_error = e
            continue

    raise RuntimeError(f"All providers and endpoints failed, last error: {last_error}")
