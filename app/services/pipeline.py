"""Glue: untrusted bytes -> validated pixels -> skin analysis -> palette. Pure CPU work, no I/O."""
from __future__ import annotations

from dataclasses import dataclass

from app.services.image_io import DecodedImage, decode_for_analysis
from app.services.palette import build_palette
from app.services.skin import SkinAnalysis, analyze_skin


@dataclass
class AnalysisBundle:
    analysis: SkinAnalysis
    palette: list[dict]
    decoded: DecodedImage


def analyze_bytes(raw: bytes, *, treat_as_skin: bool = False) -> AnalysisBundle:
    decoded = decode_for_analysis(raw)
    analysis = analyze_skin(decoded.rgb, treat_as_skin=treat_as_skin)
    if decoded.had_transparency:
        analysis.warnings.append({"code": "transparency", "message": "Transparent areas were filled with a neutral background and ignored."})
    return AnalysisBundle(analysis, build_palette(analysis.lab, analysis.undertone_key), decoded)
