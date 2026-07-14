"""Викторина для экрана-замка: выбор вопроса и проверка ответа.

Выбор — взвешенно-случайный: чем чаще человек ошибался в вопросе,
тем выше шанс, что вопрос выпадет снова (интервальное повторение
в простейшем виде).

Проверка ответа — в два рубежа: сначала мгновенное сравнение
нормализованных строк, а если не совпало — LLM-судья решает,
эквивалентен ли ответ по смыслу (формулу можно записать по-разному:
«c2=a2+b2» и «сумма квадратов катетов» — одно и то же).
"""
import random
import re
import sqlite3
from datetime import datetime

import requests

from . import config, db

def list_packs(conn: sqlite3.Connection) -> list[dict]:
    """Все наборы (включая «Мои вопросы») с флагом «включён»."""
    enabled = set(db.enabled_packs(conn))
    counts = {r["pack"]: r["n"] for r in conn.execute(
        "SELECT pack, COUNT(*) AS n FROM questions GROUP BY pack")}
    packs = [{"id": db.CUSTOM_PACK, "name": "Мои вопросы",
              "count": counts.get(db.CUSTOM_PACK, 0),
              "enabled": db.CUSTOM_PACK in enabled}]
    for p in db.load_pack_files():
        packs.append({"id": p["id"], "name": p["name"],
                      "count": counts.get(p["id"], len(p["questions"])),
                      "enabled": p["id"] in enabled})
    return packs


def pick_question(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Случайный вопрос из ВКЛЮЧЁННЫХ наборов (ошибки выпадают чаще)."""
    enabled = db.enabled_packs(conn)
    if not enabled:
        return None
    marks = ",".join("?" * len(enabled))
    rows = conn.execute(
        f"SELECT * FROM questions WHERE pack IN ({marks})", enabled).fetchall()
    if not rows:
        return None
    # вес = 1 + 2×ошибки − правильные (но не меньше 1)
    weights = [max(1, 1 + 2 * r["wrong"] - r["correct"]) for r in rows]
    return random.choices(rows, weights=weights, k=1)[0]


def record(conn: sqlite3.Connection, question_id: int | None, result: str) -> None:
    conn.execute("INSERT INTO quiz_attempts (ts, question_id, result) VALUES (?, ?, ?)",
                 (datetime.now().isoformat(timespec="seconds"), question_id, result))
    if question_id is not None:
        if result == "correct":
            conn.execute("UPDATE questions SET asked = asked + 1, correct = correct + 1 "
                         "WHERE id = ?", (question_id,))
        elif result in ("wrong", "peeked"):
            conn.execute("UPDATE questions SET asked = asked + 1, wrong = wrong + 1 "
                         "WHERE id = ?", (question_id,))
    conn.commit()


def _normalize(s: str) -> str:
    """Убираем всё, кроме букв и цифр: «C = 2·π·r» → «c2πr»."""
    s = s.lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9πа-я²³ⁿ⁻¹]", "", s)


def check_answer(question: str, correct: str, user: str) -> bool:
    if not user.strip():
        return False
    n_correct, n_user = _normalize(correct), _normalize(user)
    if n_user and (n_user == n_correct or n_user in n_correct or n_correct in n_user):
        return True
    try:
        return _llm_judge(question, correct, user)
    except Exception:
        return False        # ИИ недоступен — засчитываем только точное совпадение


def _llm_judge(question: str, correct: str, user: str) -> bool:
    prompt = (
        "Ты проверяешь ответ ученика. Вопрос: «{q}». Эталонный ответ: «{c}». "
        "Ответ ученика: «{u}». Ответ ученика может быть записан другими словами "
        "или другой нотацией — важен смысл. Если по смыслу верно, ответь строго "
        "«да», иначе строго «нет»."
    ).format(q=question, c=correct, u=user)
    r = requests.post(
        config.GROQ_URL,
        json={"model": config.GROQ_TEXT_MODEL, "temperature": 0.0,
              "messages": [{"role": "user", "content": prompt}]},
        headers={"Authorization": "Bearer " + config.load_key("groq"),
                 "User-Agent": "Mozilla/5.0 companion/1.0"},
        timeout=30,
    )
    r.raise_for_status()
    verdict = r.json()["choices"][0]["message"]["content"].strip().lower()
    return verdict.startswith("да")
