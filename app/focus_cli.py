"""Управление фокус-сессиями из консоли.

    python -m app.focus_cli "дописать курсовую" --minutes 60
    python -m app.focus_cli --status
    python -m app.focus_cli --stop
"""
import argparse
import sys
from datetime import datetime

from . import db

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Фокус-сессии Напарника")
    parser.add_argument("goal", nargs="*", help="цель сессии")
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    conn = db.connect()

    if args.stop:
        db.stop_focus(conn)
        print("Фокус-сессия остановлена.")
        return

    if args.status or not args.goal:
        focus = db.active_focus(conn)
        if focus:
            left = (datetime.fromisoformat(focus["ends_ts"]) - datetime.now()).seconds // 60
            print(f"Идёт фокус: «{focus['goal']}», осталось ~{left} мин.")
        else:
            print("Фокус-сессии нет. Запусти: python -m app.focus_cli \"цель\" --minutes 60")
        return

    goal = " ".join(args.goal)
    db.start_focus(conn, goal, args.minutes)
    print(f"Фокус на {args.minutes} мин: «{goal}». Напарник следит 👀")


if __name__ == "__main__":
    main()
