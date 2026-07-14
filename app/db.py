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

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL,
    asked    INTEGER NOT NULL DEFAULT 0,
    correct  INTEGER NOT NULL DEFAULT 0,
    wrong    INTEGER NOT NULL DEFAULT 0    -- неверные + подсмотренные
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    question_id INTEGER,
    result      TEXT NOT NULL              -- correct | wrong | peeked | parent_exit
);
"""

# Вопросы «на старт» — потом редактируются в веб-панели
SEED_QUESTIONS = [
    ("Теорема Пифагора: чему равен квадрат гипотенузы?", "сумме квадратов катетов (c² = a² + b²)"),
    ("Теорема Виета: чему равна сумма корней x² + px + q = 0?", "-p (минус p)"),
    ("Формула дискриминанта квадратного уравнения", "D = b² - 4ac"),
    ("Формула площади круга", "S = πr²"),
    ("Производная функции xⁿ", "n·xⁿ⁻¹"),
    ("Формула длины окружности", "C = 2πr"),
]

# Настройки по умолчанию (пароль родителя — «1234», меняется в панели)
DEFAULT_SETTINGS = {
    "quiz_enabled": "0",
    "quiz_mode": "fixed",       # fixed — каждые N минут; random — случайно из [min, max]
    "quiz_min": "30",
    "quiz_max": "60",
    "quiz_password_hash": "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4",
    "overlay_enabled": "1",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row      # строки как словари: row["category"]
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Дотягивает старую базу до новой схемы, сеет вопросы и настройки."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)")}
    for col, ddl in (("is_game", "INTEGER NOT NULL DEFAULT 0"),
                     ("media", "TEXT DEFAULT ''"),
                     ("apps", "TEXT DEFAULT ''")):
        if col not in cols:
            conn.execute(f"ALTER TABLE observations ADD COLUMN {col} {ddl}")

    if conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0:
        conn.executemany("INSERT INTO questions (question, answer) VALUES (?, ?)",
                         SEED_QUESTIONS)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                     (key, value))
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS.get(key, "")


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                 (key, value))
    conn.commit()


def add_observation(conn: sqlite3.Connection, obs: dict) -> None:
    conn.execute(
        "INSERT INTO observations (ts, app, category, description, is_distraction, "
        "confidence, is_game, media, apps) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"),
         obs["app"], obs["category"], obs["description"],
         int(obs["is_distraction"]), obs["confidence"],
         int(obs.get("is_game", False)), obs.get("media", ""), obs.get("apps", "")),
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
