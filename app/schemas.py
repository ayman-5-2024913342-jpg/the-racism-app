"""Pydantic request/response models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ImagePayload(BaseModel):
    image_data_url: str = Field(min_length=1, max_length=16_000_000)


class ValidatedImage(BaseModel):
    ok: Literal[True] = True
    image_data_url: str
    mime_type: Literal["image/jpeg"] = "image/jpeg"
    width: int
    height: int
    size_bytes: int
    message: str


class WarningOut(BaseModel):
    code: str
    message: str


class AnalyzeResponse(BaseModel):
    id: str
    result_url: str
    saved: bool
    shared: bool
    hex: str
    shade_label: str
    undertone_label: str
    confidence: float
    confidence_label: str
    warnings: list[WarningOut]


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
