"""Статистика: превращаем ленту наблюдений в цифры.

Ключевая идея учёта времени: каждое наблюдение "весит" столько,
сколько прошло до следующего (но не больше двойного интервала —
если компьютер спал 3 часа, это не значит, что человек 3 часа кодил).
"""
from datetime import date, datetime, timedelta

from . import config, db

MAX_GAP = config.INTERVAL_SEC * 2   # секунд; больший разрыв считаем перерывом


def day_summary(conn, day: date | None = None) -> dict:
    """Сводка за день: минуты по категориям, доля отвлечений, лента."""
    day = day or date.today()
    rows = conn.execute(
        "SELECT * FROM observations WHERE ts >= ? AND ts < ? ORDER BY ts",
        (day.isoformat(), (day + timedelta(days=1)).isoformat()),
    ).fetchall()

    by_category: dict[str, float] = {}
    distraction_sec = 0.0
    total_sec = 0.0
    timeline = []

    for i, row in enumerate(rows):
        ts = datetime.fromisoformat(row["ts"])
        if i + 1 < len(rows):
            gap = (datetime.fromisoformat(rows[i + 1]["ts"]) - ts).total_seconds()
            weight = min(gap, MAX_GAP)
        else:
            weight = config.INTERVAL_SEC          # последнему верим на один интервал

        total_sec += weight
        by_category[row["category"]] = by_category.get(row["category"], 0) + weight
        if row["is_distraction"]:
            distraction_sec += weight

        timeline.append({
            "time": ts.strftime("%H:%M"),
            "category": row["category"],
            "description": row["description"],
            "app": row["app"],
            "is_distraction": bool(row["is_distraction"]),
        })

    return {
        "date": day.isoformat(),
        "total_min": round(total_sec / 60),
        "distraction_min": round(distraction_sec / 60),
        "distraction_share": round(distraction_sec / total_sec, 2) if total_sec else 0.0,
        "by_category_min": {k: round(v / 60)
                            for k, v in sorted(by_category.items(),
                                               key=lambda kv: -kv[1])},
        "timeline": timeline,
    }


def is_productive_day(summary: dict) -> bool:
    """"Продуктивный день": хотя бы 30 минут за компьютером и отвлечений меньше 40%."""
    return summary["total_min"] >= 30 and summary["distraction_share"] < 0.4


def current_streak(conn) -> int:
    """Сколько продуктивных дней подряд, включая сегодня (если он уже продуктивен)."""
    streak = 0
    day = date.today()
    while True:
        summary = day_summary(conn, day)
        if summary["total_min"] == 0 and day == date.today():
            day -= timedelta(days=1)      # сегодня ещё пусто — начинаем со вчера
            continue
        if not is_productive_day(summary):
            break
        streak += 1
        day -= timedelta(days=1)
    return streak
