"""Иконка в системном трее: видно, что запись идёт.

Зелёный глаз — наблюдение активно, серый — пауза. В меню — счётчик
скриншотов за сегодня (честность перед пользователем: он всегда знает,
сколько раз его экран сфотографирован), пауза и выход.
"""
import os
import threading
import webbrowser

from PIL import Image, ImageDraw

from . import db

GREEN = (78, 203, 143, 255)
GRAY = (120, 126, 143, 255)


def _eye_icon(color) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 14, 60, 50], fill=color)            # веко
    d.ellipse([22, 20, 42, 44], fill=(20, 22, 30, 255))  # зрачок
    d.ellipse([27, 24, 34, 31], fill=(255, 255, 255, 255))  # блик
    return img


def start(state: dict, port: int = 8010) -> None:
    """Запускает иконку в фоновом потоке. Ошибки глотаем: трей — украшение,
    без него всё работает."""
    try:
        import pystray
    except ImportError:
        return

    def shots_today(_item) -> str:
        try:
            return f"Скриншотов сегодня: {len(db.today_observations(db.connect()))}"
        except Exception:
            return "Скриншотов сегодня: ?"

    def toggle_text(_item) -> str:
        return "⏸ Пауза" if state["watching"] else "▶ Продолжить"

    def toggle(icon, _item):
        state["watching"] = not state["watching"]
        icon.icon = _eye_icon(GREEN if state["watching"] else GRAY)

    menu = pystray.Menu(
        pystray.MenuItem(shots_today, None, enabled=False),
        pystray.MenuItem(toggle_text, toggle),
        pystray.MenuItem("Открыть панель",
                         lambda: webbrowser.open(f"http://localhost:{port}")),
        pystray.MenuItem("Выход", lambda icon: (icon.stop(), os._exit(0))),
    )
    icon = pystray.Icon("naparnik", _eye_icon(GREEN), "Напарник — наблюдение идёт", menu)
    threading.Thread(target=icon.run, daemon=True).start()
