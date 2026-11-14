"""Pixel-domain transform ladder for degrading latent (invisible) watermarks.

Metadata stripping removes the *declaration* of a watermark (e.g. a C2PA
manifest recording a c2pa.watermarked action), but a robust watermark lives in
the pixel data. The levels below apply progressively stronger perturbations
that attack such signals, trading fidelity for survivability reduction.

  L0  metadata strip only (pixel-identical, lossless)
  L1  clean re-encode (JPEG q97 / lossless WebP), no spatial changes
  L2  JPEG q90 + slight resample (x0.97, Lanczos) + faint Gaussian noise
  L3  JPEG q85 + stronger resample (x0.94) + noise + color jitter + micro-crop

Honest limitation: without access to the generator's watermark *decoder* you
cannot verify removal — you can only raise the attack strength. L3-type
transforms defeat most published robust-watermark schemes in the academic
literature, but no transform offers a guarantee.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageEnhance

from .strip import strip_file

LEVELS = (0, 1, 2, 3)


def _psnr(a: Image.Image, b: Image.Image) -> float:
    """Peak signal-to-noise ratio between two same-size RGB images (dB)."""
    import math

    from PIL import ImageChops

    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    hist = diff.histogram()
    sq = sum(value * ((i % 256) ** 2) for i, value in enumerate(hist))
    n = a.size[0] * a.size[1] * 3
    mse = sq / n
    if mse == 0:
        return float("inf")
    return 10 * math.log10(255.0**2 / mse)


def _encode(im: Image.Image, out_format: str, quality: int | None) -> bytes:
    buf = io.BytesIO()
    if out_format == "JPEG":
        im.convert("RGB").save(buf, "JPEG", quality=quality or 95,
                               subsampling=1, optimize=True)
    elif out_format == "WEBP":
        im.save(buf, "WEBP", quality=quality or 95,
                lossless=quality is None, method=6)
    else:
        im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _resample(im: Image.Image, factor: float) -> Image.Image:
    w, h = im.size
    small = im.resize((max(1, round(w * factor)), max(1, round(h * factor))),
                      Image.LANCZOS)
    return small.resize((w, h), Image.LANCZOS)


def _noise(im: Image.Image, sigma: float, seed: int) -> Image.Image:
    """Additive Gaussian noise at C speed via Image.effect_noise.

    effect_noise returns a grayscale image centered at 128 with the given
    standard deviation; we recenter it at 0 and add it to every channel.
    """
    from PIL import ImageChops

    src = im.convert("RGB")
    gray = Image.effect_noise(src.size, max(1.0, sigma * 4))
    delta = gray.point(lambda p: p - 128)
    delta_rgb = Image.merge("RGB", (delta, delta, delta))
    return ImageChops.add(src, delta_rgb)


def _color_jitter(im: Image.Image, pct: float, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    im = ImageEnhance.Contrast(im).enhance(1 + rnd.uniform(-pct, pct))
    im = ImageEnhance.Brightness(im).enhance(1 + rnd.uniform(-pct, pct))
    im = ImageEnhance.Color(im).enhance(1 + rnd.uniform(-pct, pct))
    return im


def _micro_crop(im: Image.Image, max_px: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    w, h = im.size
    l, t = rnd.randint(0, max_px), rnd.randint(0, max_px)
    r, b = rnd.randint(0, max_px), rnd.randint(0, max_px)
    cropped = im.crop((l, t, w - r, h - b))
    return cropped.resize((w, h), Image.LANCZOS)


def transform_file(
    src: str | Path,
    level: int,
    out_format: str = "auto",
    seed: int | None = None,
) -> tuple[bytes, str, float]:
    """Apply the ladder to one file.

    Returns (bytes, extension, psnr_vs_source_db). level 0 returns the
    losslessly stripped original container; levels >= 1 are re-encoded.
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    src = Path(src)
    seed = seed if seed is not None else hash(src.name) & 0xFFFF

    clean, _method = strip_file(src)
    if level == 0:
        ext = src.suffix.lstrip(".").lower() or "png"
        return clean, ext, float("inf")

    src_im = Image.open(io.BytesIO(clean))
    src_im.load()
    src_im = src_im.convert("RGB")

    if out_format == "auto":
        out_format = "JPEG"  # re-encode is the point at L1+
    elif out_format == "same":
        out_format = "PNG" if src.suffix.lower() == ".png" else "JPEG"

    im = src_im
    if level == 1:
        blob = _encode(im, out_format, quality=97)
    elif level == 2:
        im = _resample(im, 0.97)
        im = _noise(im, sigma=0.8, seed=seed)
        blob = _encode(im, out_format, quality=90)
    else:  # level 3
        im = _micro_crop(im, max_px=2, seed=seed)
        im = _resample(im, 0.96)
        im = _color_jitter(im, pct=0.015, seed=seed)
        im = _noise(im, sigma=1.2, seed=seed + 1)
        blob = _encode(im, out_format, quality=88)

    result = Image.open(io.BytesIO(blob))
    result.load()
    psnr = _psnr(src_im, result.convert("RGB"))
    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[out_format]
    return blob, ext, psnr
