"""Detect embedded provenance signals in image files.

Reports (never modifies) what provenance/metadata carriers a file contains:
  - PNG: ancillary chunks (caBX = C2PA JUMBF, tEXt/iTXt/zTXt, eXIf, tIME, ...)
  - JPEG: APP1 (Exif/XMP), APP11 (JUMBF/C2PA), APP13 (IPTC), COM, ...
  - WebP: EXIF / XMP RIFF chunks, C2PA signatures
  - Any format: raw byte signatures (c2pa, jumbf, xmp, known generator strings)

The byte-signature scan is heuristic and only used for reporting; the
structured parsers are authoritative for what will actually be removed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# PNG chunks that carry metadata/provenance (everything else ancillary or critical)
PNG_CRITICAL = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
PNG_COLOR_KEEP = {b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"pHYs"}

# Byte signatures worth flagging in a heuristic scan
BYTE_SIGNATURES = [
    (b"c2pa", "C2PA provenance data"),
    (b"jumbf", "JUMBF container (C2PA carrier)"),
    (b"http://ns.adobe.com/xap/1.0/", "XMP metadata"),
    (b"<x:xmpmeta", "XMP metadata"),
    (b"Exif\x00\x00", "EXIF metadata"),
    (b"OpenAI", "generator string: OpenAI"),
    (b"gpt-image", "generator string: gpt-image"),
    (b"DALL", "generator string: DALL-E"),
    (b"Midjourney", "generator string: Midjourney"),
    (b"Stable Diffusion", "generator string: Stable Diffusion"),
    (b"stable-diffusion", "generator string: stable-diffusion"),
    (b"ComfyUI", "generator string: ComfyUI"),
    (b"Firefly", "generator string: Adobe Firefly"),
    (b"SynthID", "generator string: SynthID reference"),
    (b"trainedAlgorithmicMedia", "IPTC digitalSourceType: trained algorithmic media"),
]


@dataclass
class DetectionReport:
    path: str
    format: str = "unknown"
    findings: list[str] = field(default_factory=list)
    declared_watermark: bool = False  # manifest declares c2pa.watermarked.*

    @property
    def clean(self) -> bool:
        return not self.findings

    def add(self, msg: str) -> None:
        if msg not in self.findings:
            self.findings.append(msg)


def _detect_png(data: bytes, rep: DetectionReport) -> None:
    rep.format = "PNG"
    off = 8
    while off + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[off : off + 8])
        body = data[off + 8 : off + 8 + length]
        if ctype not in PNG_CRITICAL and ctype not in PNG_COLOR_KEEP:
            name = ctype.decode("latin1")
            if ctype == b"caBX":
                rep.add("PNG caBX chunk: C2PA manifest (Content Credentials)")
                if b"c2pa.watermarked" in body:
                    rep.declared_watermark = True
                    rep.add("C2PA manifest declares c2pa.watermarked action "
                            "(invisible pixel watermark)")
            else:
                rep.add(f"PNG ancillary chunk: {name} ({length} bytes)")
        off += 12 + length
        if ctype == b"IEND":
            break


def _detect_jpeg(data: bytes, rep: DetectionReport) -> None:
    rep.format = "JPEG"
    off = 2  # skip SOI
    while off + 4 <= len(data):
        if data[off] != 0xFF:
            break
        marker = data[off + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            off += 2
            continue
        if marker == 0xDA:  # SOS: entropy data follows until EOI
            break
        length = struct.unpack(">H", data[off + 2 : off + 4])[0]
        body = data[off + 4 : off + 2 + length]
        seg = data[off : off + 2 + length]
        if marker == 0xE1:
            if body.startswith(b"Exif\x00\x00"):
                rep.add(f"JPEG APP1: EXIF ({length} bytes)")
            elif b"xmp" in body[:64].lower():
                rep.add(f"JPEG APP1: XMP ({length} bytes)")
                if b"c2pa" in seg:
                    rep.add("XMP contains C2PA references")
        elif marker == 0xEB:
            if b"jumb" in body[:16] or b"c2pa" in body[:64]:
                rep.add(f"JPEG APP11: JUMBF/C2PA manifest ({length} bytes)")
                if b"c2pa.watermarked" in body:
                    rep.declared_watermark = True
                    rep.add("C2PA manifest declares c2pa.watermarked action "
                            "(invisible pixel watermark)")
        elif marker == 0xED:
            rep.add(f"JPEG APP13: IPTC/Photoshop ({length} bytes)")
        elif marker == 0xFE:
            rep.add(f"JPEG COM: comment ({length} bytes)")
        elif marker in (0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
                        0xEC, 0xEE, 0xEF):
            rep.add(f"JPEG APP{marker - 0xE0}: ({length} bytes)")
        off += 2 + length


def _detect_webp(data: bytes, rep: DetectionReport) -> None:
    rep.format = "WebP"
    off = 12
    while off + 8 <= len(data):
        ctype = data[off : off + 4]
        length = struct.unpack("<I", data[off + 4 : off + 8])[0]
        if ctype in (b"EXIF", b"XMP "):
            rep.add(f"WebP chunk: {ctype.decode().strip()} ({length} bytes)")
        elif ctype not in (b"VP8 ", b"VP8L", b"VP8X", b"ICCP", b"ALPH", b"ANIM",
                           b"ANMF"):
            rep.add(f"WebP chunk: {ctype.decode('latin1')} ({length} bytes)")
        off += 8 + length + (length & 1)


def detect(path: str | Path) -> DetectionReport:
    """Inspect a file and return a report of embedded provenance signals."""
    path = Path(path)
    data = path.read_bytes()
    rep = DetectionReport(path=str(path))

    if data.startswith(PNG_SIGNATURE):
        _detect_png(data, rep)
    elif data.startswith(b"\xff\xd8\xff"):
        _detect_jpeg(data, rep)
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        _detect_webp(data, rep)
    else:
        rep.format = "other"

    # Heuristic whole-file signature scan (report-only)
    for sig, label in BYTE_SIGNATURES:
        if sig in data:
            rep.add(f"byte signature: {label}")

    return rep
