"""Batch pipeline: detect -> strip/transform -> write -> verify -> report.

Files are processed in parallel (ThreadPoolExecutor). Pillow releases the GIL
for decode/encode/resize work, so threads give near-linear speedup for the
re-encode-heavy levels while keeping the design simple and crash-isolated.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .analyzer import analyze, diff as analyze_diff, to_dict as analyze_to_dict
from .detect import detect
from .plugins import DetectorPlugin, Verdict, run_detectors
from .transform import transform_file

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


@dataclass
class FileResult:
    source: str
    output: str | None = None
    level: int = 0
    status: str = "ok"
    findings_before: list[str] = field(default_factory=list)
    declared_watermark: bool = False
    findings_after: list[str] = field(default_factory=list)
    detector_verdicts: list[dict] = field(default_factory=list)
    provenance_before: dict = field(default_factory=dict)
    provenance_after: dict = field(default_factory=dict)
    provenance_diff: dict = field(default_factory=dict)
    psnr_db: float | None = None
    bytes_in: int = 0
    bytes_out: int = 0
    error: str | None = None


def iter_images(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def _process_one(
    img: Path,
    src_root: Path,
    out_dir: Path,
    level: int,
    out_format: str,
    detectors: list[DetectorPlugin],
) -> FileResult:
    rel = img.relative_to(src_root) if src_root.is_dir() else Path(img.name)
    res = FileResult(source=str(img), level=level, bytes_in=img.stat().st_size)
    try:
        before = detect(img)
        res.findings_before = before.findings
        res.declared_watermark = before.declared_watermark
        res.provenance_before = analyze_to_dict(analyze(img))

        blob, ext, psnr = transform_file(img, level=level, out_format=out_format)
        dest = (out_dir / rel).with_suffix("." + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)

        after = detect(dest)
        res.findings_after = after.findings
        res.provenance_after = analyze_to_dict(analyze(dest))
        res.provenance_diff = analyze_diff(analyze(img), analyze(dest))
        if detectors:
            res.detector_verdicts = [
                asdict(v) for v in run_detectors(dest, detectors)
            ]
        res.output = str(dest)
        res.bytes_out = dest.stat().st_size
        res.psnr_db = None if psnr == float("inf") else round(psnr, 2)
    except Exception as exc:  # keep batch going, record failure
        res.status = "error"
        res.error = str(exc)
    return res


def process(
    src: str | Path,
    out_dir: str | Path,
    level: int = 0,
    out_format: str = "auto",
    report_path: str | Path | None = None,
    workers: int | None = None,
    detectors: list[DetectorPlugin] | None = None,
    progress: Callable[[int, int, FileResult], None] | None = None,
) -> list[FileResult]:
    src = Path(src)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    images = iter_images(src)
    results: list[FileResult] = []

    if workers is None:
        workers = min(8, (os.cpu_count() or 2))
    workers = max(1, min(workers, len(images) or 1))

    done = 0
    if workers == 1 or len(images) <= 1:
        for img in images:
            res = _process_one(img, src, out_dir, level, out_format,
                               detectors or [])
            results.append(res)
            done += 1
            if progress:
                progress(done, len(images), res)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_one, img, src, out_dir, level,
                            out_format, detectors or []): img
                for img in images
            }
            for fut in as_completed(futures):
                res = fut.result()
                results.append(res)
                done += 1
                if progress:
                    progress(done, len(images), res)

    # stable ordering by source path regardless of completion order
    results.sort(key=lambda r: r.source)

    if report_path:
        Path(report_path).write_text(
            json.dumps([asdict(r) for r in results], indent=2))
    return results


def summarize(results: list[FileResult]) -> str:
    lines = []
    ok = sum(1 for r in results if r.status == "ok")
    lines.append(f"Processed {len(results)} file(s): {ok} ok, "
                 f"{len(results) - ok} error(s)")
    has_det = any(r.detector_verdicts for r in results)
    header = f"{'file':<44} {'before':>6} {'after':>5} {'PSNR dB':>8}"
    if has_det:
        header += "  detectors"
    lines.append(header)
    for r in results:
        if r.status != "ok":
            lines.append(f"{Path(r.source).name:<44} ERROR: {r.error}")
            continue
        psnr = "inf" if r.psnr_db is None else f"{r.psnr_db:.1f}"
        row = (f"{Path(r.source).name:<44} "
               f"{len(r.findings_before):>6} "
               f"{len(r.findings_after):>5} {psnr:>8}")
        if has_det:
            flags = []
            for v in r.detector_verdicts:
                mark = ("FLAG" if v["flagged"] is True else
                        "ok" if v["flagged"] is False else "?")
                flags.append(f"{v['plugin']}:{mark}")
            row += "  " + " ".join(flags)
        lines.append(row)
    return "\n".join(lines)
