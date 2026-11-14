"""Command-line interface.

Examples:
  python -m scrubber.cli photo.png -o out/
  python -m scrubber.cli ./batch-folder -o out/ -l 2 --report report.json
  python -m scrubber.cli ./batch-folder --detect-only
  python -m scrubber.cli ./folder -l 2 --detectors metadata --detectors "shell:/opt/lab/aidec {path}"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .detect import detect
from .pipeline import iter_images, process, summarize
from .plugins import load_plugins


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="scrubber",
        description="Batch-remove provenance metadata (C2PA/EXIF/XMP/IPTC) "
                    "and apply pixel-domain watermark-degradation transforms.")
    ap.add_argument("input", help="image file or folder (recursive)")
    ap.add_argument("-o", "--out", default="scrubbed",
                    help="output directory (default: ./scrubbed)")
    ap.add_argument("-l", "--level", type=int, default=0, choices=[0, 1, 2, 3],
                    help="0=metadata strip only (lossless), 1=re-encode q97, "
                         "2=q90+resample+noise, 3=q88+stronger transforms")
    ap.add_argument("--format", default="auto",
                    choices=["auto", "same", "JPEG", "PNG", "WEBP"],
                    help="output container for levels >= 1 (default: auto)")
    ap.add_argument("--report", help="write JSON report to this path")
    ap.add_argument("--workers", type=int, default=None,
                    help="parallel workers (default: min(8, cpu_count))")
    ap.add_argument("--detectors", action="append", metavar="SPEC",
                    help="score outputs with detector plugins; repeatable. "
                         "SPECs: metadata | watermark-declared | "
                         "shell:<cmd {path}> | http:<url>")
    ap.add_argument("--detectors-config",
                    help="JSON config listing plugins (default: detectors.json "
                         "next to the CLI if present)")
    ap.add_argument("--detect-only", action="store_true",
                    help="only report embedded signals, do not write output")
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        ap.error(f"input not found: {src}")

    if args.detect_only:
        for img in iter_images(src):
            rep = detect(img)
            tag = "CLEAN" if rep.clean else f"{len(rep.findings)} finding(s)"
            print(f"[{tag}] {img}")
            for f in rep.findings:
                print(f"    - {f}")
        return 0

    detectors = None
    if args.detectors or args.detectors_config:
        detectors = load_plugins(config_path=args.detectors_config,
                                 specs=args.detectors)

    def progress(done: int, total: int, res) -> None:
        mark = "ok" if res.status == "ok" else "ERROR"
        print(f"  [{done}/{total}] {Path(res.source).name} -> {mark}",
              flush=True)

    results = process(src, args.out, level=args.level,
                      out_format=args.format, report_path=args.report,
                      workers=args.workers, detectors=detectors,
                      progress=progress)
    print(summarize(results))
    if args.report:
        print(f"Report: {args.report}")
    return 1 if any(r.status != "ok" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
