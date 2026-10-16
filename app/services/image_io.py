"""Safe image decoding for untrusted uploads.

Validation is by decoded *content* (never by filename or client MIME type). Images are decoded in
memory, EXIF-rotated, flattened onto a neutral background if transparent, and converted to a fresh
RGB buffer, which drops EXIF/GPS/ICC metadata. Nothing is written to disk.
"""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings
from app.errors import AppError

ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}  # MPO = JPEG variant some phones produce
NEUTRAL_BG = (248, 247, 242, 255)


class ImageValidationError(AppError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(code, message, status_code)


@dataclass(frozen=True)
class ImageLimits:
    max_bytes: int
    max_side: int
    max_pixels: int
    min_side: int


def limits_from_settings() -> ImageLimits:
    s = get_settings()
    return ImageLimits(s.max_upload_bytes, s.max_image_side, s.max_image_pixels, s.min_image_side)


@dataclass(frozen=True)
class OpenedImage:
    image: Image.Image  # RGB, upright, flattened
    format: str
    original_size: tuple[int, int]
    had_transparency: bool


def open_validated(raw: bytes, limits: ImageLimits | None = None) -> OpenedImage:
    limits = limits or limits_from_settings()
    if not raw:
        raise ImageValidationError("empty_file", "The file is empty.")
    if len(raw) > limits.max_bytes:
        mb = max(1, limits.max_bytes // (1024 * 1024))
        raise ImageValidationError("file_too_large", f"Please choose an image smaller than {mb} MB.", 413)
    Image.MAX_IMAGE_PIXELS = limits.max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                fmt = (probe.format or "").upper()
                if fmt not in ALLOWED_FORMATS:
                    raise ImageValidationError("unsupported_format", "Unsupported image content. Please use JPEG, PNG, or WebP.")
                w, h = probe.size
                if w < limits.min_side or h < limits.min_side:
                    raise ImageValidationError(
                        "image_too_small",
                        f"The image is too small. Choose an image at least {limits.min_side} × {limits.min_side} pixels.",
                    )
                if w > limits.max_side or h > limits.max_side or w * h > limits.max_pixels:
                    raise ImageValidationError(
                        "image_too_large",
                        f"The image dimensions are too large. Maximum supported size is {limits.max_side} × {limits.max_side} "
                        f"pixels ({limits.max_pixels // 1_000_000} megapixels).",
                    )
                probe.verify()
            with Image.open(io.BytesIO(raw)) as source:
                source.seek(0)  # first frame only for animated files
                source.load()   # full decode: catches truncated / corrupt data
                image = ImageOps.exif_transpose(source)
                transparent = False
                if image.mode in ("RGBA", "LA", "PA", "P"):
                    rgba = image.convert("RGBA")
                    transparent = rgba.getchannel("A").getextrema()[0] < 255
                    image = Image.alpha_composite(Image.new("RGBA", rgba.size, NEUTRAL_BG), rgba)
                image = image.convert("RGB")
                image.load()
                return OpenedImage(image, fmt, (w, h), transparent)
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageValidationError(
            "image_too_large",
            f"The image dimensions are too large. Maximum supported size is {limits.max_side} × {limits.max_side} "
            f"pixels ({limits.max_pixels // 1_000_000} megapixels).",
        ) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError):
        raise ImageValidationError(
            "invalid_image", "We couldn't read this image. Try a different JPEG, PNG, or WebP file."
        ) from None


def normalize_preview(raw: bytes, limits: ImageLimits | None = None) -> tuple[bytes, int, int]:
    """Return (JPEG bytes, width, height): a metadata-free, size-capped preview for the cropper."""
    opened = open_validated(raw, limits)
    image = opened.image
    cap = get_settings().max_preview_side
    if max(image.size) > cap:
        image.thumbnail((cap, cap), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
    return out.getvalue(), image.width, image.height


@dataclass(frozen=True)
class DecodedImage:
    rgb: np.ndarray  # uint8, HxWx3
    format: str
    original_size: tuple[int, int]
    analysed_size: tuple[int, int]
    had_transparency: bool


def decode_for_analysis(raw: bytes, limits: ImageLimits | None = None, max_side: int | None = None) -> DecodedImage:
    opened = open_validated(raw, limits)
    image = opened.image
    cap = max_side or get_settings().max_analysis_side
    if max(image.size) > cap:
        image.thumbnail((cap, cap), Image.Resampling.LANCZOS)
    arr = np.asarray(image, dtype=np.uint8).copy()
    return DecodedImage(arr, opened.format, opened.original_size, (arr.shape[1], arr.shape[0]), opened.had_transparency)
