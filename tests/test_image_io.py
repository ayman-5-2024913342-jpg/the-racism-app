import io

import pytest
from PIL import Image

from app.services.image_io import (
    ImageLimits, ImageValidationError, decode_for_analysis, normalize_preview, open_validated,
)
from tests.helpers import encode, skin_image

LIM = ImageLimits(max_bytes=2_000_000, max_side=6000, max_pixels=4_000_000, min_side=32)


def decode(raw, **kw):
    return decode_for_analysis(raw, LIM, max_side=kw.get("max_side", 640))


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_accepts_supported_formats(fmt):
    out = decode(encode(skin_image(), fmt))
    assert out.rgb.shape == (240, 240, 3) and out.rgb.dtype.name == "uint8"


def test_rejects_empty_garbage_and_truncated():
    good = encode(skin_image(size=300))
    for blob in (b"", b"not an image at all", b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, good[: len(good) // 2]):
        with pytest.raises(ImageValidationError):
            decode(blob)


def test_rejects_gif_even_if_valid_image():
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "red").save(buf, format="GIF")
    with pytest.raises(ImageValidationError) as e:
        decode(buf.getvalue())
    assert e.value.code == "unsupported_format" and e.value.status_code == 422


def test_limits_bytes_pixels_side_and_tiny():
    big = encode(skin_image(size=300))
    with pytest.raises(ImageValidationError) as e:
        open_validated(big, ImageLimits(100, 6000, 4_000_000, 32))
    assert e.value.code == "file_too_large" and e.value.status_code == 413
    with pytest.raises(ImageValidationError) as e:
        open_validated(big, ImageLimits(2_000_000, 6000, 1000, 32))
    assert e.value.code == "image_too_large"
    with pytest.raises(ImageValidationError) as e:
        open_validated(big, ImageLimits(2_000_000, 200, 4_000_000, 32))
    assert e.value.code == "image_too_large"
    with pytest.raises(ImageValidationError) as e:
        open_validated(encode(skin_image(size=20)), LIM)
    assert e.value.code == "image_too_small"


def test_downscales_for_analysis_and_flattens_transparency():
    assert max(decode(encode(skin_image(size=900))).rgb.shape[:2]) == 640
    buf = io.BytesIO()
    Image.new("RGBA", (100, 100), (255, 0, 0, 0)).save(buf, format="PNG")
    out = decode(buf.getvalue())
    assert out.had_transparency and out.rgb[0, 0].tolist() == [248, 247, 242]


def test_exif_orientation_applied_and_metadata_dropped():
    img = Image.fromarray(skin_image(size=240)[:, :160])  # 240 tall x 160 wide
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate: width/height swap
    exif[0x010F] = "SecretCameraMaker"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    out = decode(buf.getvalue())
    assert out.rgb.shape[:2] == (160, 240)
    jpeg, w, h = normalize_preview(buf.getvalue(), LIM)
    assert (w, h) == (240, 160)
    assert len(Image.open(io.BytesIO(jpeg)).getexif()) == 0


def test_content_not_extension():
    assert decode(encode(skin_image(), "PNG")).format == "PNG"
