#!/usr/bin/env bash
# Build a noarch .deb for provenance-scrubber (source install, depends on Python).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.1.0}"
OUT="build/deb/provenance-scrubber_${VERSION}_all.deb"
STAGE="build/deb/root"
LIBDIR="usr/lib/provenance-scrubber"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/$LIBDIR" \
         "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/scalable/apps"

# source tree
cp -r scrubber "$STAGE/$LIBDIR/scrubber"
cp cli_main.py desktop_gui.py webapp.py "$STAGE/$LIBDIR/"

# wrappers
printf '#!/bin/sh\nexec python3 /usr/lib/provenance-scrubber/cli_main.py "$@"\n' > "$STAGE/usr/bin/provenance-scrubber"
printf '#!/bin/sh\nexec python3 /usr/lib/provenance-scrubber/desktop_gui.py "$@"\n' > "$STAGE/usr/bin/provenance-scrubber-gui"
chmod 755 "$STAGE/usr/bin/provenance-scrubber" "$STAGE/usr/bin/provenance-scrubber-gui"

# desktop entry + icons
install -m 644 packaging/provenance-scrubber.desktop "$STAGE/usr/share/applications/provenance-scrubber.desktop"
install -m 644 packaging/provenance-scrubber.svg "$STAGE/usr/share/icons/hicolor/scalable/apps/provenance-scrubber.svg"
for sz in 16 24 32 48 64 96 128 256 512; do
  install -Dm 644 "packaging/icons/hicolor/${sz}x${sz}/apps/provenance-scrubber.png" \
    "$STAGE/usr/share/icons/hicolor/${sz}x${sz}/apps/provenance-scrubber.png"
done

cp packaging/debian/control "$STAGE/DEBIAN/control"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
rm -rf "$STAGE"
echo "built $OUT"
