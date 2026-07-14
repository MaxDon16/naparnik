"""Веб-сервер Напарника: FastAPI + фоновый наблюдатель.

Один процесс делает всё: uvicorn отдаёт панель и API, а отдельный
поток крутит цикл наблюдения. Общее состояние (последнее наблюдение,
последняя реплика) лежит в словаре STATE — простейший способ связать
поток наблюдения и веб-запросы.

Запуск:  uvicorn app.server:app --port 8010
"""
import hashlib
import random
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import companion, config, db, quiz, reporter, tray, watcher

app = FastAPI(title="Напарник")

STATE = {
    "watching": True,          # наблюдение включено?
    "last_obs": None,          # последнее наблюдение (dict)
    "last_remark": None,       # последняя реплика Напарника
    "last_ts": None,
    "next_quiz_ts": None,      # когда всплывёт следующий вопрос
}


def _watch_loop() -> None:
    """Фоновый поток: наблюдает, пока STATE['watching'] == True."""
    conn = db.connect()        # у потока своё соединение с SQLite
    while True:
        if STATE["watching"]:
            obs = watcher.observe_once(conn)
            if obs:
                STATE["last_obs"] = obs
                STATE["last_ts"] = datetime.now().strftime("%H:%M:%S")
                remark = watcher.react(conn, obs)
                if remark:
                    STATE["last_remark"] = remark
        time.sleep(config.INTERVAL_SEC)


def _quiz_loop() -> None:
    """Фоновый поток экрана-замка: ждёт свой интервал и запускает вопрос.

    Экран открывается ОТДЕЛЬНЫМ процессом: у tkinter будет свой главный
    поток, а падение окна не заденет сервер.
    """
    conn = db.connect()
    while True:
        if db.get_setting(conn, "quiz_enabled") != "1":
            STATE["next_quiz_ts"] = None
            time.sleep(10)
            continue

        lo = max(1, int(db.get_setting(conn, "quiz_min") or 30))
        hi = max(lo, int(db.get_setting(conn, "quiz_max") or 60))
        mode = db.get_setting(conn, "quiz_mode")
        delay = lo * 60 if mode == "fixed" else random.randint(lo * 60, hi * 60)
        STATE["next_quiz_ts"] = (datetime.now() + timedelta(seconds=delay)).strftime("%H:%M")

        # спим мелкими шагами, чтобы выключение сработало сразу
        deadline = time.time() + delay
        cancelled = False
        while time.time() < deadline:
            time.sleep(5)
            if db.get_setting(conn, "quiz_enabled") != "1":
                cancelled = True
                break
        if not cancelled:
            subprocess.call([sys.executable, "-m", "app.lockscreen"],
                            cwd=config.PROJECT_DIR)


OVERLAY = {"proc": None}


def _overlay_running() -> bool:
    return OVERLAY["proc"] is not None and OVERLAY["proc"].poll() is None


def _overlay_start() -> None:
    if not _overlay_running():
        OVERLAY["proc"] = subprocess.Popen(
            [sys.executable, "-m", "app.overlay"], cwd=config.PROJECT_DIR)


def _overlay_stop() -> None:
    if _overlay_running():
        OVERLAY["proc"].terminate()
    OVERLAY["proc"] = None


threading.Thread(target=_watch_loop, daemon=True).start()
threading.Thread(target=_quiz_loop, daemon=True).start()
tray.start(STATE)
if db.get_setting(db.connect(), "overlay_enabled") != "0":
    _overlay_start()


# --- API ---

class FocusRequest(BaseModel):
    goal: str
    minutes: int = 60


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class WatchRequest(BaseModel):
    on: bool


class QuizSettings(BaseModel):
    enabled: bool
    mode: str = "fixed"            # fixed | random
    min_minutes: int = 30
    max_minutes: int = 60
    new_password: str | None = None


class QuestionRequest(BaseModel):
    question: str
    answer: str


@app.get("/api/status")
def status():
    conn = db.connect()
    focus = db.active_focus(conn)
    return {
        "watching": STATE["watching"],
        "interval_sec": config.INTERVAL_SEC,
        "last_obs": STATE["last_obs"],
        "last_ts": STATE["last_ts"],
        "last_remark": STATE["last_remark"],
        "focus": dict(focus) if focus else None,
        "streak": reporter.current_streak(conn),
        "next_quiz_ts": STATE["next_quiz_ts"],
    }


@app.post("/api/watch")
def toggle_watch(req: WatchRequest):
    STATE["watching"] = req.on
    return {"watching": STATE["watching"]}


@app.get("/api/today")
def today():
    return reporter.day_summary(db.connect())


@app.get("/api/evening")
def evening():
    return {"text": companion.evening_report(db.connect())}


@app.post("/api/focus")
def start_focus(req: FocusRequest):
    conn = db.connect()
    db.start_focus(conn, req.goal, req.minutes)
    return {"ok": True}


@app.delete("/api/focus")
def stop_focus():
    db.stop_focus(db.connect())
    STATE["last_remark"] = None
    return {"ok": True}


@app.post("/api/chat")
def chat(req: ChatRequest):
    return {"reply": companion.chat(db.connect(), req.message, req.history)}


# --- Тренировка памяти (экран-замок) ---

@app.get("/api/quiz")
def quiz_info():
    conn = db.connect()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    attempts = conn.execute(
        "SELECT result, COUNT(*) AS n FROM quiz_attempts WHERE ts >= ? GROUP BY result",
        (week_ago,)).fetchall()
    return {
        "enabled": db.get_setting(conn, "quiz_enabled") == "1",
        "mode": db.get_setting(conn, "quiz_mode"),
        "min_minutes": int(db.get_setting(conn, "quiz_min")),
        "max_minutes": int(db.get_setting(conn, "quiz_max")),
        "next_quiz_ts": STATE["next_quiz_ts"],
        "questions": [dict(q) for q in conn.execute(
            "SELECT * FROM questions ORDER BY wrong DESC, id").fetchall()],
        "week_stats": {r["result"]: r["n"] for r in attempts},
        "packs": quiz.list_packs(),
        "overlay": _overlay_running(),
    }


@app.post("/api/quiz/packs/{pack_id}/import")
def import_pack(pack_id: str):
    added = quiz.import_pack(db.connect(), pack_id)
    return {"ok": True, "added": added}


@app.post("/api/overlay")
def toggle_overlay(req: WatchRequest):
    conn = db.connect()
    db.set_setting(conn, "overlay_enabled", "1" if req.on else "0")
    _overlay_start() if req.on else _overlay_stop()
    return {"overlay": _overlay_running()}


@app.post("/api/quiz/settings")
def quiz_settings(req: QuizSettings):
    conn = db.connect()
    db.set_setting(conn, "quiz_enabled", "1" if req.enabled else "0")
    db.set_setting(conn, "quiz_mode", req.mode if req.mode in ("fixed", "random") else "fixed")
    db.set_setting(conn, "quiz_min", str(max(1, req.min_minutes)))
    db.set_setting(conn, "quiz_max", str(max(req.min_minutes, req.max_minutes)))
    if req.new_password:
        db.set_setting(conn, "quiz_password_hash",
                       hashlib.sha256(req.new_password.encode()).hexdigest())
    if not req.enabled:
        STATE["next_quiz_ts"] = None
    return {"ok": True}


@app.post("/api/quiz/questions")
def add_question(req: QuestionRequest):
    conn = db.connect()
    conn.execute("INSERT INTO questions (question, answer) VALUES (?, ?)",
                 (req.question.strip(), req.answer.strip()))
    conn.commit()
    return {"ok": True}


@app.delete("/api/quiz/questions/{qid}")
def delete_question(qid: int):
    conn = db.connect()
    conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
    conn.commit()
    return {"ok": True}


@app.post("/api/quiz/launch")
def launch_quiz():
    """Кнопка «Проверить сейчас»: открыть экран-замок немедленно."""
    subprocess.Popen([sys.executable, "-m", "app.lockscreen"],
                     cwd=config.PROJECT_DIR)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent.parent / "static" / "index.html")
