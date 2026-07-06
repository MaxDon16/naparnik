"""Сводка дня в консоли: python -m app.report_cli"""
import sys

from . import companion, db, reporter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> None:
    conn = db.connect()
    summary = reporter.day_summary(conn)

    print(f"\n=== День {summary['date']} ===")
    print(f"За компьютером: ~{summary['total_min']} мин, "
          f"отвлечения: {summary['distraction_min']} мин "
          f"({summary['distraction_share']:.0%})")
    for cat, minutes in summary["by_category_min"].items():
        print(f"  {cat:12} {minutes:4} мин")
    print(f"Серия продуктивных дней: {reporter.current_streak(conn)}")

    print("\n--- Напарник говорит ---")
    print(companion.evening_report(conn))


if __name__ == "__main__":
    main()
