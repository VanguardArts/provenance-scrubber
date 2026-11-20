#!/usr/bin/env bash
# Build a portable AppImage of the Provenance Scrubber GUI (python-appimage).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="build/appimage"
PKG="provenance-scrubber"
APP="com.vanguardarts.ProvenanceScrubber"
ARCH="x86_64"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"

mkdir -p "$OUT"
[ -x "$OUT/appimagetool" ] || { curl -fsSL "$APPIMAGETOOL_URL" -o "$OUT/appimagetool"; chmod +x "$OUT/appimagetool"; }

APPDIR="$OUT/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/provenance-scrubber"

cp -r scrubber "$APPDIR/usr/lib/provenance-scrubber/scrubber"
cp cli_main.py desktop_gui.py webapp.py "$APPDIR/usr/lib/provenance-scrubber/"

cat > "$APPDIR/usr/bin/provenance-scrubber-gui" <<'RUN'
#!/bin/sh
HERE="/usr/lib/provenance-scrubber"
exec python3 "$HERE/desktop_gui.py" "$@"
RUN
chmod +x "$APPDIR/usr/bin/provenance-scrubber-gui"

cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec python3 "$HERE/usr/lib/provenance-scrubber/desktop_gui.py" "$@"
RUN
chmod +x "$APPDIR/AppRun"

install -Dm644 packaging/flatpak/com.vanguardarts.ProvenanceScrubber.desktop "$APPDIR/$APP.desktop"
install -Dm644 packaging/icons/hicolor/256x256/apps/provenance-scrubber.png "$APPDIR/$APP.png"

ARCH="$ARCH" "$OUT/appimagetool" "$APPDIR" "$OUT/$PKG-${ARCH}.AppImage"
echo "✔ AppImage built: $OUT/$PKG-${ARCH}.AppImage"
