#!/usr/bin/env bash
# Portable install for image-scrub (no root — installs to $PREFIX).
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN="$PREFIX/bin"
APPS="$PREFIX/share/applications"
ICONS="$PREFIX/share/icons/hicolor"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBDIR="$PREFIX/lib/image-scrub"

mkdir -p "$BIN" "$APPS" "$ICONS/scalable/apps" "$LIBDIR"

rm -rf "$LIBDIR/image_scrub"
cp -r "$SRC_DIR/image_scrub" "$LIBDIR/image_scrub"
cp "$SRC_DIR/cli_main.py" "$SRC_DIR/desktop_gui.py" "$SRC_DIR/webapp.py" "$LIBDIR/"

printf '#!/bin/sh\nexec python3 "%s/cli_main.py" "$@"\n' "$LIBDIR" > "$BIN/image-scrub"
printf '#!/bin/sh\nexec python3 "%s/desktop_gui.py" "$@"\n' "$LIBDIR" > "$BIN/image-scrub-gui"
chmod 755 "$BIN/image-scrub" "$BIN/image-scrub-gui"

install -m 644 "$SRC_DIR/packaging/image-scrub.desktop" "$APPS/image-scrub.desktop"
install -m 644 "$SRC_DIR/packaging/image-scrub.svg" "$ICONS/scalable/apps/image-scrub.svg"
for sz in 16 24 32 48 64 96 128 256 512; do
    install -Dm 644 "$SRC_DIR/packaging/icons/hicolor/${sz}x${sz}/apps/image-scrub.png" \
        "$ICONS/${sz}x${sz}/apps/image-scrub.png"
done

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true

echo "✔ Image Scrub installed to $PREFIX"
echo "  CLI:  image-scrub"
echo "  GUI:  image-scrub-gui"
