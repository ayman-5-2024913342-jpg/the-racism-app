"""JSON API: validation previews and the analysis endpoint."""
from __future__ import annotations

import base64
import binascii
import logging
import threading

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import session_scope
from app.errors import AppError
from app.repositories import AnalysisRepository, OwnerRepository
from app.schemas import AnalyzeResponse, ImagePayload, ValidatedImage, WarningOut
from app.services.image_io import ImageValidationError, normalize_preview
from app.services.pipeline import analyze_bytes
from app.services.ratelimit import RateLimiter

logger = logging.getLogger("the_great_app")
router = APIRouter(prefix="/api")
MAX_NAME_LEN = 40

_settings = get_settings()
_limiter = RateLimiter(_settings.rate_limit_per_minute)
_gate = threading.BoundedSemaphore(_settings.max_concurrent_analyses)  # caps simultaneous CPU-heavy analyses


async def read_limited(file: UploadFile, limit: int) -> bytes:
    """Read an upload in chunks and stop as soon as it exceeds the limit."""
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ImageValidationError(
                    "file_too_large", f"Please choose an image smaller than {max(1, limit // (1024 * 1024))} MB.", 413
                )
            chunks.append(chunk)
    finally:
        await file.close()
    return b"".join(chunks)


def _preview_response(raw: bytes, message: str) -> ValidatedImage:
    jpeg, width, height = normalize_preview(raw)
    encoded = base64.b64encode(jpeg).decode("ascii")
    return ValidatedImage(
        image_data_url=f"data:image/jpeg;base64,{encoded}", width=width, height=height,
        size_bytes=len(jpeg), message=message,
    )


@router.post("/upload", response_model=ValidatedImage, name="upload_image")
async def upload_image(file: UploadFile = File(...)):
    """Validate image content and return a metadata-stripped, size-capped preview. Nothing is persisted."""
    raw = await read_limited(file, get_settings().max_upload_bytes)
    return await run_in_threadpool(_preview_response, raw, "Image checked and safely re-encoded. It has not been saved.")


@router.post("/confirm-crop", response_model=ValidatedImage, name="confirm_crop")
async def confirm_crop(payload: ImagePayload):
    """Validate the browser-confirmed crop; nothing is persisted."""
    url = payload.image_data_url
    if not url.startswith("data:image/") or ";base64," not in url:
        raise AppError("bad_crop", "The crop payload must be a base64-encoded image.", 422)
    header, encoded = url.split(",", 1)
    if header not in {"data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"}:
        raise AppError("bad_crop", "Unsupported crop format. Use JPEG, PNG, or WebP.", 422)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise AppError("bad_crop", "The crop image data is malformed.", 422) from None
    return await run_in_threadpool(
        _preview_response, raw, "Crop confirmed and checked. It is not saved until you choose to save the result."
    )


def clean_name(raw: str | None) -> str:
    """Trim, collapse whitespace, require 1-40 printable characters."""
    name = " ".join((raw or "").split())
    if not name:
        raise AppError("name_required", "Please enter your name before analyzing.", 422)
    if len(name) > MAX_NAME_LEN:
        raise AppError("name_too_long", f"Please keep your name to {MAX_NAME_LEN} characters or fewer.", 422)
    if not name.isprintable():
        raise AppError("name_invalid", "Your name contains characters we can't use.", 422)
    return name


def _process(raw: bytes, owner_token: str, treat_as_skin: bool, save: bool | None, name: str) -> AnalyzeResponse:
    """CPU-bound image analysis + DB write; runs in a worker thread, never on the event loop."""
    s = get_settings()
    with _gate:
        bundle = analyze_bytes(raw, treat_as_skin=treat_as_skin)
    with session_scope() as db:
        owner = OwnerRepository(db, s.secret_key).get_or_create(owner_token)
        saved = owner.save_by_default if save is None else bool(save)
        shared = saved and owner.share_by_default
        repo = AnalysisRepository(db)
        repo.purge_expired()
        row = repo.create(owner.id, bundle, saved=saved, shared=shared, ttl_hours=s.result_ttl_hours, name=name)
        out = AnalyzeResponse(
            id=row.id, result_url=f"/results/{row.id}", saved=row.saved, shared=row.shared, hex=row.hex,
            shade_label=row.shade_label, undertone_label=row.undertone_label,
            confidence=round(row.confidence, 3), confidence_label=row.confidence_label,
            warnings=[WarningOut(**w) for w in row.warnings],
        )
    logger.info("analysis complete samples=%d reliability=%.2f saved=%s", bundle.analysis.n_samples, bundle.analysis.confidence, saved)
    return out


@router.post("/analyze", response_model=AnalyzeResponse, name="analyze_image")
async def analyze_image(
    request: Request,
    file: UploadFile = File(...),
    treat_as_skin: bool = Form(False),
    save: bool | None = Form(None),
    name: str = Form(""),
):
    """Analyse a confirmed crop. The image is processed in memory and discarded; only computed values are stored."""
    _limiter.check(request.state.owner_token)
    name = clean_name(name)
    raw = await read_limited(file, get_settings().max_upload_bytes)
    return await run_in_threadpool(_process, raw, request.state.owner_token, treat_as_skin, save, name)
