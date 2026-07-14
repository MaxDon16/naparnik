"""Плавающая иконка поверх всех окон: «запись идёт».

Маленькая тёмная «таблетка» с глазом и счётчиком скриншотов за сегодня.
Живёт отдельным процессом (python -m app.overlay), статус берёт у сервера.

Управление:
  перетаскивание — зажать и вести мышью;
  двойной клик   — открыть веб-панель;
  правый клик    — скрыть (до перезапуска сервера или кнопки в панели).
"""
import argparse
import tkinter as tk
import webbrowser

import requests

BG = "#1b1e27"
GOOD = "#4ecb8f"
GRAY = "#787e8f"
TEXT = "#e8eaf0"
API = "http://127.0.0.1:8010/api/status"


class Overlay:
    def __init__(self, autoclose: int | None = None):
        self.root = tk.Tk()
        self.root.overrideredirect(True)              # без рамки
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        # стартуем в правом нижнем углу, над панелью задач
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"96x34+{sw - 120}+{sh - 90}")

        self.label = tk.Label(self.root, text="👁 …", bg=BG, fg=GOOD,
                              font=("Segoe UI", 12, "bold"))
        self.label.pack(expand=True, fill="both")

        for w in (self.root, self.label):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<Double-Button-1>",
                   lambda e: webbrowser.open("http://localhost:8010"))
            w.bind("<Button-3>", lambda e: self.root.destroy())

        if autoclose:
            self.root.after(autoclose * 1000, self.root.destroy)

        self._refresh()
        self._stay_on_top()

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _stay_on_top(self):
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        except tk.TclError:
            return
        self.root.after(2000, self._stay_on_top)

    def _refresh(self):
        """Раз в 10 секунд спрашиваем сервер: идёт ли запись и сколько кадров."""
        try:
            s = requests.get(API, timeout=3).json()
            count = 0
            # число скриншотов = число наблюдений за сегодня
            t = requests.get("http://127.0.0.1:8010/api/today", timeout=3).json()
            count = len(t.get("timeline", []))
            if s.get("watching"):
                self.label.config(text=f"👁 {count}", fg=GOOD)
            else:
                self.label.config(text=f"⏸ {count}", fg=GRAY)
        except Exception:
            self.label.config(text="👁 ?", fg=GRAY)   # сервер не отвечает
        self.root.after(10_000, self._refresh)

    def run(self):
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--autoclose", type=int, default=None)
    args = parser.parse_args()
    Overlay(autoclose=args.autoclose).run()


if __name__ == "__main__":
    main()
