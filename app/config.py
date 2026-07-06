"""Настройки Напарника.

Все "ручки" проекта в одном месте: интервал наблюдения, модели,
пути к ключам и базе. Меняешь здесь — работает везде.
"""
from pathlib import Path

# --- Наблюдение ---
INTERVAL_SEC = 150          # как часто делать скриншот (2.5 минуты)
MAX_WIDTH = 1280            # до какой ширины сжимать скриншот перед отправкой
JPEG_QUALITY = 60           # качество JPEG (меньше = меньше трафика)

# --- Провайдеры ИИ ---
# Основной — Groq (быстрый, бесплатный). Запасной — Gemini через локальный прокси.
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"

# Запасной провайдер — OpenRouter (бесплатные модели, но бывает 429-throttle)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
OPENROUTER_TEXT_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"

REQUEST_TIMEOUT = 60        # секунд на ответ API

# --- Пути ---
PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "companion.db"


def load_key(provider: str) -> str:
    """Ключ API из ~/.{provider}/key.txt (та же схема, что в ask.py)."""
    key_file = Path.home() / f".{provider}" / "key.txt"
    return key_file.read_text(encoding="utf-8").strip()


# Категории активности. Модель обязана выбрать ровно одну из этого списка —
# так статистика не расползётся на сотню формулировок.
CATEGORIES = [
    "код",          # программирование, IDE, терминал
    "учёба",        # конспекты, учебники, курсы, задачи
    "документы",    # тексты, таблицы, презентации, отчёты
    "общение",      # мессенджеры, почта
    "видео",        # YouTube, фильмы, стримы
    "игры",
    "соцсети",      # ленты, шортсы, тиктоки
    "браузинг",     # поиск, чтение статей
    "творчество",   # графика, музыка, монтаж
    "другое",
]
