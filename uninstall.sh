#!/usr/bin/env bash
# Uninstall provenance-scrubber (portable install only).
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
LIBDIR="$PREFIX/lib/provenance-scrubber"

rm -rf "$LIBDIR"
rm -f "$PREFIX/bin/provenance-scrubber" "$PREFIX/bin/provenance-scrubber-gui"
rm -f "$PREFIX/share/applications/provenance-scrubber.desktop"
rm -f "$PREFIX/share/icons/hicolor/scalable/apps/provenance-scrubber.svg"
for sz in 16 24 32 48 64 96 128 256 512; do
    rm -f "$PREFIX/share/icons/hicolor/${sz}x${sz}/apps/provenance-scrubber.png"
done

echo "✔ Provenance Scrubber uninstalled from $PREFIX"
