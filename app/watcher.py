"""Цикл наблюдения — сердце Напарника.

Каждые INTERVAL_SEC секунд: скриншот → vision-ИИ → запись в базу.
Запуск:
    python -m app.watcher --once      # один такт, для проверки
    python -m app.watcher             # бесконечное наблюдение (Ctrl+C — стоп)
"""
import argparse
import sys
import time

from . import capture, config, db, vision

# Консоль Windows по умолчанию в cp1251 и падает на юникод-символах
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def observe_once(conn) -> dict | None:
    """Один такт наблюдения. Возвращает наблюдение или None при ошибке."""
    image = capture.take_screenshot()
    try:
        obs = vision.classify(image)
    except vision.VisionError as e:
        print(f"  ! ИИ недоступен, такт пропущен: {e}", file=sys.stderr)
        return None
    db.add_observation(conn, obs)
    return obs


def react(conn, obs: dict) -> str | None:
    """Реплика Напарника на наблюдение (если есть повод).

    Во время фокус-сессии реагируем на любое отвлечение,
    вне фокуса — молчим: без цели дёргать человека невежливо.
    """
    if not obs["is_distraction"]:
        return None
    focus = db.active_focus(conn)
    if focus is None:
        return None
    from . import companion                  # ленивый импорт: не тянуть LLM без нужды
    try:
        return companion.distraction_remark(obs, goal=focus["goal"])
    except Exception:
        return f"Эй, мы же договорились: {focus['goal']}!"   # запасная реплика без ИИ


def main() -> None:
    parser = argparse.ArgumentParser(description="Напарник: наблюдение за активностью")
    parser.add_argument("--once", action="store_true", help="один такт и выход")
    parser.add_argument("--interval", type=int, default=config.INTERVAL_SEC,
                        help="пауза между тактами, сек")
    args = parser.parse_args()

    conn = db.connect()
    print(f"Напарник смотрит (интервал {args.interval} c, Ctrl+C — стоп)...")

    while True:
        obs = observe_once(conn)
        if obs:
            mark = "⚠ отвлечение" if obs["is_distraction"] else "✓"
            print(f"[{time.strftime('%H:%M:%S')}] {mark} {obs['category']}: "
                  f"{obs['description']} ({obs['app']}, {obs['confidence']:.0%})")
            remark = react(conn, obs)
            if remark:
                print(f"  💬 Напарник: {remark}")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
