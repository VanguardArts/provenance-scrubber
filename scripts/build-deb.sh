#!/usr/bin/env bash
# Build a noarch .deb for image-scrub (source install, depends on Python).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.4.0}"
OUT="build/deb/image-scrub_${VERSION}_all.deb"
STAGE="build/deb/root"
LIBDIR="usr/lib/image-scrub"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/$LIBDIR" \
         "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/scalable/apps"

# source tree
cp -r image_scrub "$STAGE/$LIBDIR/image_scrub"
cp cli_main.py desktop_gui.py webapp.py "$STAGE/$LIBDIR/"

# wrappers
printf '#!/bin/sh\nexec python3 /usr/lib/image-scrub/cli_main.py "$@"\n' > "$STAGE/usr/bin/image-scrub"
printf '#!/bin/sh\nexec python3 /usr/lib/image-scrub/desktop_gui.py "$@"\n' > "$STAGE/usr/bin/image-scrub-gui"
chmod 755 "$STAGE/usr/bin/image-scrub" "$STAGE/usr/bin/image-scrub-gui"

# desktop entry + icons
install -m 644 packaging/image-scrub.desktop "$STAGE/usr/share/applications/image-scrub.desktop"
install -m 644 packaging/image-scrub.svg "$STAGE/usr/share/icons/hicolor/scalable/apps/image-scrub.svg"
for sz in 16 24 32 48 64 96 128 256 512; do
  install -Dm 644 "packaging/icons/hicolor/${sz}x${sz}/apps/image-scrub.png" \
    "$STAGE/usr/share/icons/hicolor/${sz}x${sz}/apps/image-scrub.png"
done

cp packaging/debian/control "$STAGE/DEBIAN/control"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
rm -rf "$STAGE"
echo "built $OUT"
