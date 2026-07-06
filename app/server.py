"""Веб-сервер Напарника: FastAPI + фоновый наблюдатель.

Один процесс делает всё: uvicorn отдаёт панель и API, а отдельный
поток крутит цикл наблюдения. Общее состояние (последнее наблюдение,
последняя реплика) лежит в словаре STATE — простейший способ связать
поток наблюдения и веб-запросы.

Запуск:  uvicorn app.server:app --port 8010
"""
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import companion, config, db, reporter, watcher

app = FastAPI(title="Напарник")

STATE = {
    "watching": True,          # наблюдение включено?
    "last_obs": None,          # последнее наблюдение (dict)
    "last_remark": None,       # последняя реплика Напарника
    "last_ts": None,
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


threading.Thread(target=_watch_loop, daemon=True).start()


# --- API ---

class FocusRequest(BaseModel):
    goal: str
    minutes: int = 60


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class WatchRequest(BaseModel):
    on: bool


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


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent.parent / "static" / "index.html")
