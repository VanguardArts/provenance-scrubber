"""Pixel-domain invisible-watermark decoders (optional heavy dependencies).

These decode watermarks that live in the *pixels* rather than in metadata, so
they can confirm — independently of any C2PA declaration — whether a latent
watermark actually survived a scrub. They are deliberately behind optional
imports: the ML stack is large and not required for the rest of the tool.

Currently implemented:

  ``stable-signature`` (Meta, ICCV 2023)
      Decodes the 48-bit signature that Stable-Signature diffusion models embed,
      using Meta's public pre-trained HiDDeN extractor (a TorchScript CNN). The
      false-positive rate is the exact Binomial(48, 0.5) upper tail from the
      paper (Eq. 2). This is a genuine decoder — forensic *when you hold the
      signing key* — not a heuristic.
"""

from __future__ import annotations

import math
from pathlib import Path

# Meta's public, whitened HiDDeN extractor (48-bit). Reference:
#   facebookresearch/stable_signature
EXTRACTOR_URL = (
    "https://dl.fbaipublicfiles.com/ssl_watermarking/"
    "dec_48b_whit.torchscript.pt"
)
NBITS = 48

# ImageNet mean/std the extractor expects.
_MEAN = [0.485, 0.456, 0.406]
_STD = [0.229, 0.224, 0.225]


def default_cache_dir() -> Path:
    return Path.home() / ".cache" / "provenance-scrubber"


def _extractor_path(cache_dir: Path | None) -> Path:
    return (cache_dir or default_cache_dir()) / "dec_48b_whit.torchscript.pt"


def _ensure_extractor(cache_dir: Path | None, download: bool) -> Path:
    path = _extractor_path(cache_dir)
    if path.exists():
        return path
    if not download:
        raise FileNotFoundError(
            f"extractor not cached at {path}; re-run with download enabled")
    import urllib.request

    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(EXTRACTOR_URL, path)
    return path


def binomial_pvalue(matches: int, nbits: int = NBITS) -> float:
    """P(>= matches) under Binomial(nbits, 0.5) — the Stable Signature FPR."""
    if matches <= 0:
        return 1.0
    if matches > nbits:
        return 0.0
    try:
        from scipy.special import betainc
        return float(betainc(matches, nbits - matches + 1, 0.5))
    except Exception:
        total = sum(math.comb(nbits, i) for i in range(matches, nbits + 1))
        return total * (0.5 ** nbits)


def parse_key(key: str) -> list[int]:
    bits = [int(c) for c in str(key).strip() if c in "01"]
    if len(bits) != NBITS:
        raise ValueError(f"key must be {NBITS} bits (0/1), got {len(bits)}")
    return bits


def decode_stable_signature(
    path: str | Path,
    key: str | None = None,
    cache_dir: Path | None = None,
    download: bool = True,
) -> dict:
    """Extract the 48-bit Stable-Signature code from an image.

    Returns a JSON-safe dict. ``error`` is set (and ``available`` False) when
    optional deps are missing or the decode fails. If ``key`` is provided and
    decodes, ``flagged`` is True when p < 1e-6 (i.e. a match at forensic
    confidence).
    """
    try:
        import torch  # noqa: F401
        import torchvision.transforms as T  # noqa: F401
        from PIL import Image
    except ImportError as exc:
        return {"available": False,
                "error": f"optional dependency missing: {exc}"}

    try:
        model_path = _ensure_extractor(cache_dir, download)
        model = torch.jit.load(str(model_path), map_location="cpu")
        model.eval()
        transform = T.Compose([
            T.Resize(256),
            T.CenterCrop(256),
            T.ToTensor(),
            T.Normalize(mean=_MEAN, std=_STD),
        ])
        image = Image.open(path).convert("RGB")
        x = transform(image).unsqueeze(0)
        with torch.no_grad():
            out = model(x)
        # The extractor emits 48 logits (possibly wrapped in a tuple/list).
        while isinstance(out, (tuple, list)):
            out = out[0]
        out = out.squeeze().detach().cpu().numpy()
    except Exception as exc:  # pragma: no cover - model/IO dependent
        return {"available": True, "error": str(exc)}

    bits = [1 if v > 0 else 0 for v in out[:NBITS]]
    result = {
        "available": True,
        "scheme": "stable-signature",
        "nbits": NBITS,
        "extracted_bits": "".join(map(str, bits)),
    }

    if key is not None:
        key_bits = parse_key(key)
        matches = sum(a == b for a, b in zip(bits, key_bits))
        p = binomial_pvalue(matches)
        result.update({
            "matching_bits": matches,
            "bit_accuracy": matches / NBITS,
            "p_value": p,
            "flagged": p < 1e-6,
        })
    return result
