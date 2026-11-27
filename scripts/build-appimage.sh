#!/usr/bin/env bash
# Build a portable AppImage of the Image Scrub GUI (python-appimage).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="build/appimage"
PKG="image-scrub"
APP="com.vanguardarts.ImageScrub"
ARCH="x86_64"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"

mkdir -p "$OUT"
[ -x "$OUT/appimagetool" ] || { curl -fsSL "$APPIMAGETOOL_URL" -o "$OUT/appimagetool"; chmod +x "$OUT/appimagetool"; }

APPDIR="$OUT/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/image-scrub"

cp -r image_scrub "$APPDIR/usr/lib/image-scrub/image_scrub"
cp cli_main.py desktop_gui.py webapp.py "$APPDIR/usr/lib/image-scrub/"

cat > "$APPDIR/usr/bin/image-scrub-gui" <<'RUN'
#!/bin/sh
HERE="/usr/lib/image-scrub"
exec python3 "$HERE/desktop_gui.py" "$@"
RUN
chmod +x "$APPDIR/usr/bin/image-scrub-gui"

cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec python3 "$HERE/usr/lib/image-scrub/desktop_gui.py" "$@"
RUN
chmod +x "$APPDIR/AppRun"

install -Dm644 packaging/flatpak/com.vanguardarts.ImageScrub.desktop "$APPDIR/$APP.desktop"
install -Dm644 packaging/icons/hicolor/256x256/apps/image-scrub.png "$APPDIR/$APP.png"

ARCH="$ARCH" "$OUT/appimagetool" "$APPDIR" "$OUT/$PKG-${ARCH}.AppImage"
echo "✔ AppImage built: $OUT/$PKG-${ARCH}.AppImage"
