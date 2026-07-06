"""Хранилище наблюдений — SQLite.

Одна таблица observations: каждая строка = "в такой-то момент человек
делал то-то". Из этих строк потом собирается вся статистика и отчёты.
"""
import sqlite3
from datetime import datetime, date, timedelta

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,          -- момент наблюдения, ISO-строка
    app            TEXT,
    category       TEXT NOT NULL,
    description    TEXT,
    is_distraction INTEGER NOT NULL,       -- 0/1, SQLite не имеет bool
    confidence     REAL
);
CREATE INDEX IF NOT EXISTS idx_obs_ts ON observations (ts);

CREATE TABLE IF NOT EXISTS focus_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    goal       TEXT NOT NULL,              -- «дописать курсовую»
    started_ts TEXT NOT NULL,
    ends_ts    TEXT NOT NULL,
    stopped    INTEGER NOT NULL DEFAULT 0  -- 1 = остановлена вручную
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row      # строки как словари: row["category"]
    conn.executescript(SCHEMA)
    return conn


def add_observation(conn: sqlite3.Connection, obs: dict) -> None:
    conn.execute(
        "INSERT INTO observations (ts, app, category, description, is_distraction, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"),
         obs["app"], obs["category"], obs["description"],
         int(obs["is_distraction"]), obs["confidence"]),
    )
    conn.commit()


def today_observations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Все наблюдения за сегодня, по времени."""
    return conn.execute(
        "SELECT * FROM observations WHERE ts >= ? ORDER BY ts",
        (date.today().isoformat(),),
    ).fetchall()


# --- Фокус-сессии ---

def start_focus(conn: sqlite3.Connection, goal: str, minutes: int) -> None:
    stop_focus(conn)                        # одна активная сессия за раз
    now = datetime.now()
    conn.execute(
        "INSERT INTO focus_sessions (goal, started_ts, ends_ts) VALUES (?, ?, ?)",
        (goal, now.isoformat(timespec="seconds"),
         (now + timedelta(minutes=minutes)).isoformat(timespec="seconds")),
    )
    conn.commit()


def stop_focus(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE focus_sessions SET stopped = 1 WHERE stopped = 0")
    conn.commit()


def active_focus(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Текущая фокус-сессия, если идёт."""
    return conn.execute(
        "SELECT * FROM focus_sessions WHERE stopped = 0 AND ends_ts > ? "
        "ORDER BY id DESC LIMIT 1",
        (datetime.now().isoformat(timespec="seconds"),),
    ).fetchone()
