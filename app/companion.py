"""Напарник — характер и речь.

Все реплики (вечерний отчёт, реакции на отвлечения, чат) генерирует
текстовая LLM, а личность задаётся одним системным промптом.
Хочешь другой характер — правь PERSONALITY, код трогать не нужно.
"""
import json

import requests

from . import config, reporter

PERSONALITY = """Ты — Напарник, ИИ-компаньон продуктивности студента.
Характер: дружелюбный, слегка ироничный, поддерживающий. Никогда не ругаешь
и не стыдишь — подкалываешь по-доброму, как хороший друг рядом.
Говоришь коротко и живо, по-русски, без канцелярита и без смайликов-спама
(один эмодзи на реплику — максимум). Обращаешься на «ты»."""


def _llm(prompt: str, temperature: float = 0.7) -> str:
    """Текстовый запрос с характером Напарника. Groq → Gemini (через прокси)."""
    try:
        r = requests.post(
            config.GROQ_URL,
            json={"model": config.GROQ_TEXT_MODEL,
                  "temperature": temperature,
                  "messages": [{"role": "system", "content": PERSONALITY},
                               {"role": "user", "content": prompt}]},
            headers={"Authorization": "Bearer " + config.load_key("groq"),
                     "User-Agent": "Mozilla/5.0 companion/1.0"},
            timeout=config.REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        r = requests.post(
            config.OPENROUTER_URL,
            json={"model": config.OPENROUTER_TEXT_MODEL,
                  "temperature": temperature,
                  "messages": [{"role": "system", "content": PERSONALITY},
                               {"role": "user", "content": prompt}]},
            headers={"Authorization": "Bearer " + config.load_key("openrouter"),
                     "HTTP-Referer": "http://localhost", "X-Title": "companion"},
            timeout=config.REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def evening_report(conn) -> str:
    """Вечерняя сводка дня устами Напарника."""
    summary = reporter.day_summary(conn)
    if summary["total_min"] == 0:
        return "Сегодня я тебя за компьютером почти не видел. Отдых — тоже дело 🙂"

    streak = reporter.current_streak(conn)
    prompt = (
        "Составь короткий вечерний отчёт о дне пользователя (4-6 предложений). "
        "Обязательно: чем он занимался больше всего, сколько ушло на отвлечения, "
        "одна конкретная похвала и один мягкий совет на завтра. "
        f"Серия продуктивных дней: {streak}. Если серия >= 2 — обязательно упомяни её.\n"
        f"Данные дня (JSON): {json.dumps(summary, ensure_ascii=False)}"
    )
    return _llm(prompt)


def distraction_remark(obs: dict, goal: str | None = None) -> str:
    """Короткая реплика, когда человек отвлёкся (особенно во время фокус-сессии)."""
    context = f"Человек поставил цель: «{goal}». " if goal else ""
    prompt = (
        f"{context}Сейчас он отвлёкся: {obs['category']} — {obs['description']} "
        f"({obs['app']}). Скажи ОДНУ короткую реплику (максимум 15 слов), "
        "чтобы по-дружески вернуть его к делу. Без нотаций."
    )
    return _llm(prompt, temperature=0.9)


def chat(conn, message: str, history: list[dict] | None = None) -> str:
    """Свободный разговор с Напарником. Он знает статистику сегодняшнего дня."""
    summary = reporter.day_summary(conn)
    prompt = (
        f"Статистика дня пользователя (JSON): {json.dumps(summary, ensure_ascii=False)}\n"
        f"История диалога: {json.dumps(history or [], ensure_ascii=False)}\n"
        f"Пользователь пишет: {message}\nОтветь как Напарник."
    )
    return _llm(prompt)
