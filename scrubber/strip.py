"""Lossless removal of metadata/provenance carriers.

PNG  : chunk surgery — keeps critical + color-management chunks, drops the rest
       (pixels untouched, IDAT copied verbatim).
JPEG : marker surgery — drops APP1/APP11/APP13/COM and other non-essential
       APPn segments (entropy-coded data copied verbatim).
WebP : RIFF surgery — drops EXIF/XMP chunks and recomputes VP8X flags.
Other: falls back to decode + clean re-encode via Pillow (re-encoded pixels).
"""

from __future__ import annotations

import struct
from pathlib import Path

from .detect import PNG_SIGNATURE, PNG_CRITICAL, PNG_COLOR_KEEP


class StripError(Exception):
    pass


def strip_png(data: bytes) -> bytes:
    out = bytearray(data[:8])
    off = 8
    while off + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[off : off + 8])
        seg = data[off : off + 12 + length]
        if ctype in PNG_CRITICAL or ctype in PNG_COLOR_KEEP:
            out += seg
        off += 12 + length
        if ctype == b"IEND":
            break
    if not out.endswith(b"IEND\xaeB`\x82"):
        raise StripError("PNG: IEND not found, file may be truncated")
    return bytes(out)


# JPEG segments that are safe/provenanceneutral to keep
_JPEG_KEEP_APP = {0xE0, 0xEE}  # APP0 (JFIF), APP14 (Adobe color transform)
_JPEG_KEEP_OTHER = {0xC0, 0xC1, 0xC2, 0xC4, 0xC8, 0xCC, 0xDB, 0xDD}  # SOF0/1/2, DHT, JPG, DAC, DQT, DRI


def strip_jpeg(data: bytes) -> bytes:
    if not data.startswith(b"\xff\xd8"):
        raise StripError("JPEG: missing SOI")
    out = bytearray(data[:2])
    off = 2
    while off + 4 <= len(data):
        if data[off] != 0xFF:
            raise StripError(f"JPEG: bad marker at offset {off}")
        marker = data[off + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            off += 2
            continue
        length = struct.unpack(">H", data[off + 2 : off + 4])[0]
        seg = data[off : off + 2 + length]
        if marker == 0xDA:  # SOS — copy header + all entropy data verbatim
            out += data[off:]
            return bytes(out)
        if marker in _JPEG_KEEP_APP or marker in _JPEG_KEEP_OTHER:
            out += seg
        # everything else (APP1 Exif/XMP, APP11 JUMBF, APP13 IPTC, COM, ...) dropped
        off += 2 + length
    raise StripError("JPEG: SOS not found, file may be truncated")


def strip_webp(data: bytes) -> bytes:
    if not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        raise StripError("WebP: bad RIFF header")
    out_chunks = bytearray()
    has_vp8x = False
    off = 12
    while off + 8 <= len(data):
        ctype = data[off : off + 4]
        length = struct.unpack("<I", data[off + 4 : off + 8])[0]
        seg = data[off : off + 8 + length + (length & 1)]
        if ctype == b"VP8X":
            has_vp8x = True
            # Clear EXIF (bit 3) and XMP (bit 2) flags in the VP8X feature byte
            body = bytearray(data[off + 8 : off + 8 + length])
            body[0] &= 0b11110011
            seg = b"VP8X" + struct.pack("<I", length) + bytes(body) + b"\x00" * (length & 1)
            out_chunks += seg
        elif ctype in (b"EXIF", b"XMP "):
            pass  # dropped
        else:
            out_chunks += seg
        off += 8 + length + (length & 1)
    if not has_vp8x:
        # No VP8X means no metadata carriers existed; nothing to do
        return data
    riff = b"RIFF" + struct.pack("<I", 4 + len(out_chunks)) + b"WEBP" + bytes(out_chunks)
    return riff


def strip_fallback(path: Path) -> bytes:
    """Decode + clean re-encode for formats without a lossless path."""
    import io

    from PIL import Image

    with Image.open(path) as im:
        im.load()
        buf = io.BytesIO()
        fmt = im.format or "PNG"
        if fmt == "PNG":
            im.save(buf, "PNG", optimize=True)
        elif fmt in ("JPEG", "MPO"):
            im.convert("RGB").save(buf, "JPEG", quality=97)
        elif fmt == "WEBP":
            im.save(buf, "WEBP", lossless=True)
        else:
            im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def strip_file(src: str | Path) -> tuple[bytes, str]:
    """Return (clean_bytes, method) for a source image file."""
    src = Path(src)
    data = src.read_bytes()
    if data.startswith(PNG_SIGNATURE):
        return strip_png(data), "png-chunk-surgery"
    if data.startswith(b"\xff\xd8\xff"):
        return strip_jpeg(data), "jpeg-marker-surgery"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return strip_webp(data), "webp-riff-surgery"
    return strip_fallback(src), "reencode-fallback"
