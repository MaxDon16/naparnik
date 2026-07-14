"""Экран-замок: неубираемое окно с вопросом.

Запускается ОТДЕЛЬНЫМ процессом (python -m app.lockscreen) — так
падение окна не роняет сервер, а tkinter получает свой главный поток.

Закрыть окно можно только:
  - правильным ответом на вопрос;
  - родительским паролем (хранится хешем в настройках).
Кнопка «Показать ответ» показывает ответ, но задаёт СЛЕДУЮЩИЙ вопрос.

Флаги для проверки: --demo (окно, не на весь экран, можно закрыть),
--autoclose N (закрыться через N секунд — для автотестов).
"""
import argparse
import hashlib
import tkinter as tk

from . import db, quiz

BG, CARD, TEXT, MUTED, ACCENT, BAD, GOOD = (
    "#12141a", "#1b1e27", "#e8eaf0", "#8a90a3", "#6c9bff", "#ff7a6c", "#4ecb8f")


class LockScreen:
    def __init__(self, demo: bool = False, autoclose: int | None = None):
        self.conn = db.connect()
        self.demo = demo
        self.root = tk.Tk()
        self.root.title("Напарник: вопрос!")
        self.root.configure(bg=BG)

        if demo:
            self.root.geometry("820x560+200+120")
        else:
            self.root.attributes("-fullscreen", True)
            self.root.attributes("-topmost", True)
            # без рамки → нет крестика, Alt+F4 не работает
            self.root.overrideredirect(True)
            self.root.protocol("WM_DELETE_WINDOW", lambda: None)
            self._keep_on_top()

        if autoclose:
            self.root.after(autoclose * 1000, self.root.destroy)

        self._build_ui()
        self._next_question()

    def _keep_on_top(self):
        """Каждые 700 мс возвращаем окно наверх и забираем фокус."""
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            return
        self.root.after(700, self._keep_on_top)

    def _build_ui(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(wrap, text="🔒 Пауза! Вопрос на память", bg=BG, fg=MUTED,
                 font=("Segoe UI", 14)).pack(pady=(0, 18))

        self.q_label = tk.Label(wrap, text="", bg=BG, fg=TEXT, wraplength=760,
                                justify="center", font=("Segoe UI", 22, "bold"))
        self.q_label.pack(pady=(0, 24))

        self.entry = tk.Entry(wrap, font=("Segoe UI", 16), width=40, bg=CARD,
                              fg=TEXT, insertbackground=TEXT, relief="flat",
                              justify="center")
        self.entry.pack(ipady=8)
        self.entry.bind("<Return>", lambda e: self._submit())
        self.entry.focus_set()

        btns = tk.Frame(wrap, bg=BG)
        btns.pack(pady=16)
        tk.Button(btns, text="Ответить", command=self._submit, bg=ACCENT,
                  fg="#0d1020", font=("Segoe UI", 13, "bold"), relief="flat",
                  padx=24, pady=6).pack(side="left", padx=6)
        tk.Button(btns, text="Показать ответ (будет новый вопрос)",
                  command=self._peek, bg=CARD, fg=MUTED,
                  font=("Segoe UI", 11), relief="flat", padx=14, pady=6).pack(side="left", padx=6)

        self.feedback = tk.Label(wrap, text="", bg=BG, fg=MUTED,
                                 wraplength=760, font=("Segoe UI", 14))
        self.feedback.pack(pady=(4, 0))

        # родительский пароль — маленькая строка внизу экрана
        pw = tk.Frame(self.root, bg=BG)
        pw.place(relx=0.5, rely=0.94, anchor="center")
        tk.Label(pw, text="родительский пароль:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", padx=4)
        self.pw_entry = tk.Entry(pw, show="•", width=16, bg=CARD, fg=TEXT,
                                 insertbackground=TEXT, relief="flat")
        self.pw_entry.pack(side="left", ipady=3)
        self.pw_entry.bind("<Return>", lambda e: self._parent_exit())

    def _next_question(self):
        self.question = quiz.pick_question(self.conn)
        if self.question is None:      # вопросов нет — держать экран не за что
            self.root.destroy()
            return
        self.q_label.config(text=self.question["question"])
        self.entry.delete(0, "end")

    def _submit(self):
        answer = self.entry.get()
        if not answer.strip():
            return
        self.feedback.config(text="проверяю…", fg=MUTED)
        self.root.update_idletasks()
        ok = quiz.check_answer(self.question["question"],
                               self.question["answer"], answer)
        if ok:
            quiz.record(self.conn, self.question["id"], "correct")
            self.feedback.config(text="✔ Верно! Продолжай 🙂", fg=GOOD)
            self.root.after(900, self.root.destroy)
        else:
            quiz.record(self.conn, self.question["id"], "wrong")
            self.feedback.config(text="✘ Неверно, попробуй ещё раз", fg=BAD)
            self.entry.delete(0, "end")

    def _peek(self):
        quiz.record(self.conn, self.question["id"], "peeked")
        answer = self.question["answer"]
        self._next_question()
        self.feedback.config(
            text=f"Ответ был: {answer}\nЗапомни! А вот новый вопрос:", fg=ACCENT)

    def _parent_exit(self):
        entered = hashlib.sha256(self.pw_entry.get().encode()).hexdigest()
        if entered == db.get_setting(self.conn, "quiz_password_hash"):
            quiz.record(self.conn, None, "parent_exit")
            self.root.destroy()
        else:
            self.pw_entry.delete(0, "end")

    def run(self):
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--autoclose", type=int, default=None)
    args = parser.parse_args()
    LockScreen(demo=args.demo, autoclose=args.autoclose).run()


if __name__ == "__main__":
    main()
