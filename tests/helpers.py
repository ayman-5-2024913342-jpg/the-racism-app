"""Synthetic test images (no real people's photos are used)."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


def skin_image(skin=(224, 172, 145), bg=(40, 90, 160), size=240, noise=4.0, seed=1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    arr = np.zeros((size, size, 3), dtype=np.float64)
    arr[:] = bg
    yy, xx = np.mgrid[:size, :size]
    inside = ((xx - size / 2) ** 2 / (0.4 * size) ** 2 + (yy - size / 2) ** 2 / (0.45 * size) ** 2) <= 1
    arr[inside] = skin
    arr += rng.normal(0, noise, arr.shape)
    return np.clip(arr, 0, 255).astype(np.uint8)


def flat_skin(skin=(224, 172, 145), size=200, noise=4.0, seed=2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    arr = np.full((size, size, 3), skin, dtype=np.float64) + rng.normal(0, noise, (size, size, 3))
    return np.clip(arr, 0, 255).astype(np.uint8)


def encode(arr: np.ndarray, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format=fmt)
    return buf.getvalue()
