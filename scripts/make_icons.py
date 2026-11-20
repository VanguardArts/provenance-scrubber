#!/usr/bin/env python3
"""Generate the Provenance Scrubber PNG icon set from the canonical SVG."""
import os
import cairosvg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "packaging", "provenance-scrubber.svg")
ICON_DIR = os.path.join(ROOT, "packaging", "icons", "hicolor")


def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    for size in (16, 24, 32, 48, 64, 96, 128, 256, 512):
        out_dir = os.path.join(ICON_DIR, f"{size}x{size}", "apps")
        os.makedirs(out_dir, exist_ok=True)
        cairosvg.svg2png(url=SVG, write_to=os.path.join(out_dir, "provenance-scrubber.png"),
                         output_width=size, output_height=size)
    print("icons written to", ICON_DIR)


if __name__ == "__main__":
    main()
