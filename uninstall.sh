#!/usr/bin/env bash
# Uninstall image-scrub (portable install only).
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
LIBDIR="$PREFIX/lib/image-scrub"

rm -rf "$LIBDIR"
rm -f "$PREFIX/bin/image-scrub" "$PREFIX/bin/image-scrub-gui"
rm -f "$PREFIX/share/applications/image-scrub.desktop"
rm -f "$PREFIX/share/icons/hicolor/scalable/apps/image-scrub.svg"
for sz in 16 24 32 48 64 96 128 256 512; do
    rm -f "$PREFIX/share/icons/hicolor/${sz}x${sz}/apps/image-scrub.png"
done

echo "✔ Image Scrub uninstalled from $PREFIX"
