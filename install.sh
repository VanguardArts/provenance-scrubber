#!/usr/bin/env bash
# Portable install for provenance-scrubber (no root — installs to $PREFIX).
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN="$PREFIX/bin"
APPS="$PREFIX/share/applications"
ICONS="$PREFIX/share/icons/hicolor"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBDIR="$PREFIX/lib/provenance-scrubber"

mkdir -p "$BIN" "$APPS" "$ICONS/scalable/apps" "$LIBDIR"

rm -rf "$LIBDIR/scrubber"
cp -r "$SRC_DIR/scrubber" "$LIBDIR/scrubber"
cp "$SRC_DIR/cli_main.py" "$SRC_DIR/desktop_gui.py" "$SRC_DIR/webapp.py" "$LIBDIR/"

printf '#!/bin/sh\nexec python3 "%s/cli_main.py" "$@"\n' "$LIBDIR" > "$BIN/provenance-scrubber"
printf '#!/bin/sh\nexec python3 "%s/desktop_gui.py" "$@"\n' "$LIBDIR" > "$BIN/provenance-scrubber-gui"
chmod 755 "$BIN/provenance-scrubber" "$BIN/provenance-scrubber-gui"

install -m 644 "$SRC_DIR/packaging/provenance-scrubber.desktop" "$APPS/provenance-scrubber.desktop"
install -m 644 "$SRC_DIR/packaging/provenance-scrubber.svg" "$ICONS/scalable/apps/provenance-scrubber.svg"
for sz in 16 24 32 48 64 96 128 256 512; do
    install -Dm 644 "$SRC_DIR/packaging/icons/hicolor/${sz}x${sz}/apps/provenance-scrubber.png" \
        "$ICONS/${sz}x${sz}/apps/provenance-scrubber.png"
done

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true

echo "✔ Provenance Scrubber installed to $PREFIX"
echo "  CLI:  provenance-scrubber"
echo "  GUI:  provenance-scrubber-gui"
