"""Классификация активности по скриншоту.

Скриншот кодируется в base64 и отправляется мультимодальной модели
вместе с инструкцией: "верни строго JSON — чем занят человек".
Основной провайдер — Groq (llama-4-scout), запасной — Gemini через прокси.
"""
import base64
import json
import re

import requests

from . import config

SYSTEM_PROMPT = f"""Ты — анализатор активности за компьютером.
Тебе дают скриншот экрана. Внимательно рассмотри его и верни СТРОГО JSON без пояснений:

{{
  "app": "конкретное название программы/сайта на переднем плане (например: VS Code, YouTube, Dota 2, Telegram)",
  "apps_open": ["другие видимые окна/вкладки, до 5 штук"],
  "category": "одна из: {', '.join(config.CATEGORIES)}",
  "description": "детально, 7-15 слов: ЧТО ИМЕННО делает человек",
  "is_game": true/false,
  "media_platform": "youtube | tiktok | vk | twitch | kinopoisk | другая | нет",
  "is_distraction": true/false,
  "confidence": 0.0-1.0
}}

Правила:
- category — РОВНО одно слово из списка, ничего другого.
- Будь максимально конкретен: если это игра — назови игру ("играет в Minecraft, строит дом");
  если видео — платформу и тему ролика ("смотрит на YouTube обзор видеокарты");
  если код — язык и над чем работает ("пишет Python, модуль работы с базой данных");
  если сайт — назови сайт. Названия бери из заголовков окон и вкладок, если они видны.
- is_game = true только если на экране сама игра (не магазин игр, не видео об игре).
- media_platform — только если человек СМОТРИТ видео/ленту, иначе "нет".
- is_distraction = true для развлечений (видео, игры, соцсети, ленты). Работа, учёба, код, документы — false.
- confidence — насколько ты уверен (размытый/пустой экран = низкая уверенность).
- Не пересказывай личное содержимое переписок и документов, только тип занятия."""


class VisionError(Exception):
    """Оба провайдера недоступны или вернули мусор."""


def classify(image_bytes: bytes) -> dict:
    """Скриншот → словарь с полями app, category, description, is_distraction, confidence.

    Пробует Groq, при ошибке — Gemini. Если оба упали, бросает VisionError:
    вызывающий код решает, что делать (пропустить такт наблюдения).
    """
    b64 = base64.b64encode(image_bytes).decode()
    errors = []
    for provider in (_ask_groq, _ask_openrouter):
        try:
            return _parse_answer(provider(b64))
        except Exception as e:                      # сеть, лимиты, кривой JSON
            errors.append(f"{provider.__name__}: {e}")
    raise VisionError(" | ".join(errors))


def _ask_groq(b64: str) -> str:
    body = {
        "model": config.GROQ_VISION_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": SYSTEM_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
    }
    r = requests.post(
        config.GROQ_URL,
        json=body,
        headers={"Authorization": "Bearer " + config.load_key("groq"),
                 "User-Agent": "Mozilla/5.0 companion/1.0"},
        timeout=config.REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _ask_openrouter(b64: str) -> str:
    """Запасной провайдер. API совместим с OpenAI — тело почти как у Groq."""
    body = {
        "model": config.OPENROUTER_VISION_MODEL,
        "temperature": 0.2,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": SYSTEM_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
    }
    r = requests.post(
        config.OPENROUTER_URL,
        json=body,
        headers={"Authorization": "Bearer " + config.load_key("openrouter"),
                 "HTTP-Referer": "http://localhost", "X-Title": "companion"},
        timeout=config.REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _parse_answer(text: str) -> dict:
    """Достаёт JSON из ответа модели и приводит поля к ожидаемым типам."""
    match = re.search(r"\{.*\}", text, re.DOTALL)   # на случай болтовни вокруг JSON
    if not match:
        raise ValueError(f"в ответе нет JSON: {text[:200]}")
    data = json.loads(match.group())

    category = str(data.get("category", "другое")).strip().lower()
    if category not in config.CATEGORIES:
        category = "другое"

    apps_open = data.get("apps_open", [])
    if not isinstance(apps_open, list):
        apps_open = []
    media = str(data.get("media_platform", "нет")).strip().lower()

    return {
        "app": str(data.get("app", ""))[:100],
        "apps": ", ".join(str(a)[:40] for a in apps_open[:5]),
        "category": category,
        "description": str(data.get("description", ""))[:200],
        "is_game": bool(data.get("is_game", False)),
        "media": "" if media in ("нет", "none", "") else media[:30],
        "is_distraction": bool(data.get("is_distraction", False)),
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
    }
