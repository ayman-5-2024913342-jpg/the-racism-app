"""Distribution data and chart rendering.

The measured variable is L* (CIELAB lightness) of the sampled patch in each photo. It is a
property of the *photo*, not a ranking of people. Synthetic demonstration data is generated
with a fixed seed and is always labelled as synthetic, both on the page and inside the chart.
"""
from __future__ import annotations

import io

import numpy as np
from matplotlib.figure import Figure

BIN_EDGES = np.arange(10, 100, 5.0)
SUPPRESS_BELOW = 5


def synthetic_lightness(n: int = 600, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    parts = [rng.normal(72, 8, int(n * 0.35)), rng.normal(58, 9, int(n * 0.40)), rng.normal(38, 9, n - int(n * 0.35) - int(n * 0.40))]
    return np.clip(np.concatenate(parts), 12, 95)


def histogram(values: np.ndarray, suppress: bool) -> list[dict]:
    counts, edges = np.histogram(values, bins=BIN_EDGES)
    rows = []
    for c, lo, hi in zip(counts, edges[:-1], edges[1:]):
        hidden = suppress and 0 < c < SUPPRESS_BELOW
        rows.append({"lo": float(lo), "hi": float(hi), "count": 0 if hidden else int(c), "hidden": bool(hidden)})
    return rows


def render_chart(values: np.ndarray, *, synthetic: bool) -> bytes:
    rows = histogram(values, suppress=not synthetic)
    fig = Figure(figsize=(8, 4.2), dpi=150, facecolor="#FAF7F2")
    ax = fig.subplots()
    ax.set_facecolor("#FFFFFF")
    ax.bar([r["lo"] for r in rows], [r["count"] for r in rows], width=4.6, align="edge",
           color="#B58968" if not synthetic else "#C9BBA6", edgecolor="#8A6A52", linewidth=0.8)
    ax.set_xlabel("Sampled lightness L* in the photo (a property of the image, not a ranking of people)", fontsize=8)
    ax.set_ylabel("Number of analyses", fontsize=9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#EFE9DE")
    ax.set_axisbelow(True)
    tag = "SYNTHETIC DEMONSTRATION DATA - not real users" if synthetic else "Anonymous opt-in contributions"
    ax.set_title(f"{tag}   (n = {len(values)})", fontsize=10, color="#B0402E" if synthetic else "#2B2B2B", loc="left")
    if not synthetic:
        fig.text(0.01, 0.01, f"Bars with fewer than {SUPPRESS_BELOW} analyses are hidden to protect privacy.", fontsize=7, color="#6B645A")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()
