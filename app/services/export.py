"""Export helpers: JSON document and a palette PNG drawn with Pillow."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from app.services.color import on_color

DISCLAIMER = (
    "Approximate estimate from one photo. Lighting, exposure, makeup, filters and camera "
    "processing all change the result. Not a calibrated measurement or a beauty score."
)


def palette_png(skin_hex: str, shade: str, undertone: str, palette: list[dict]) -> bytes:
    sw, pad, top = 150, 20, 120
    width = pad + (sw + pad) * (len(palette) + 1)
    im = Image.new("RGB", (width, top + sw + 90), "#FAF7F2")
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default()
    d.text((pad, 24), "THE GREAT APP - colour estimate", fill="#2B2B2B", font=font)
    d.text((pad, 48), f"Shade band: {shade}   Undertone: {undertone}", fill="#2B2B2B", font=font)
    items = [{"name": "Sampled", "hex": skin_hex}] + palette
    for i, it in enumerate(items):
        x = pad + i * (sw + pad)
        d.rounded_rectangle([x, top, x + sw, top + sw], radius=16, fill=it["hex"], outline="#E4DDD0")
        rgb = tuple(int(it["hex"][j:j + 2], 16) for j in (1, 3, 5))
        d.text((x + 10, top + sw - 24), it["hex"], fill=on_color(rgb), font=font)
        d.text((x, top + sw + 10), it["name"], fill="#2B2B2B", font=font)
    d.text((pad, top + sw + 50), DISCLAIMER[:150], fill="#6B645A", font=font)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()
