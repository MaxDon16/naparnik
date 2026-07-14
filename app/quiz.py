"""Викторина для экрана-замка: выбор вопроса и проверка ответа.

Выбор — взвешенно-случайный: чем чаще человек ошибался в вопросе,
тем выше шанс, что вопрос выпадет снова (интервальное повторение
в простейшем виде).

Проверка ответа — в два рубежа: сначала мгновенное сравнение
нормализованных строк, а если не совпало — LLM-судья решает,
эквивалентен ли ответ по смыслу (формулу можно записать по-разному:
«c2=a2+b2» и «сумма квадратов катетов» — одно и то же).
"""
import json
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import requests

from . import config, db

PACKS_DIR = Path(__file__).parent / "packs"


def list_packs() -> list[dict]:
    """Готовые наборы вопросов из app/packs/*.json."""
    packs = []
    for f in sorted(PACKS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            packs.append({"id": data["id"], "name": data["name"],
                          "count": len(data["questions"])})
        except Exception:
            continue        # битый файл набора не должен ломать всё
    return packs


def import_pack(conn: sqlite3.Connection, pack_id: str) -> int:
    """Добавляет вопросы набора, пропуская уже существующие. Возвращает число новых."""
    if not re.fullmatch(r"[\w-]+", pack_id):        # защита от ../../ в пути
        raise ValueError("bad pack id")
    path = PACKS_DIR / f"{pack_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = {row["question"] for row in conn.execute("SELECT question FROM questions")}
    added = 0
    for item in data["questions"]:
        if item["q"] not in existing:
            conn.execute("INSERT INTO questions (question, answer) VALUES (?, ?)",
                         (item["q"], item["a"]))
            added += 1
    conn.commit()
    return added


def pick_question(conn: sqlite3.Connection) -> sqlite3.Row | None:
    rows = conn.execute("SELECT * FROM questions").fetchall()
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
