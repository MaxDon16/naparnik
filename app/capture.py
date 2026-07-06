"""Захват экрана.

mss делает "сырой" снимок экрана за миллисекунды, Pillow сжимает его
в маленький JPEG — именно его мы отправим vision-модели. Оригинал
нигде не сохраняется: скриншот живёт только в оперативной памяти.
"""
import io

import mss
from PIL import Image

from . import config


def take_screenshot(max_width: int = config.MAX_WIDTH,
                    quality: int = config.JPEG_QUALITY) -> bytes:
    """Снимок основного монитора, ужатый в JPEG. Возвращает байты картинки."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]          # [0] — все мониторы разом, [1] — основной
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.rgb)

    if img.width > max_width:
        new_height = round(img.height * max_width / img.width)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


if __name__ == "__main__":
    # Быстрая самопроверка: python -m app.capture
    data = take_screenshot()
    print(f"скриншот снят: {len(data) / 1024:.0f} КБ")
