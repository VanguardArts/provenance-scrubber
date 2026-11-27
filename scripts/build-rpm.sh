#!/usr/bin/env bash
# Build a noarch .rpm for image-scrub.
# Needs: rpmbuild (and a source tarball named image-scrub-<ver>.tar.gz).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.4.0}"
TOPDIR="build/rpm"

rm -rf "$TOPDIR"
mkdir -p "$TOPDIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# make a clean source tarball with the required top-level dir
SRC="build/rpm-src/image-scrub-$VERSION"
rm -rf "build/rpm-src"
mkdir -p "$SRC"
cp -r image_scrub cli_main.py desktop_gui.py webapp.py packaging LICENSE README.md "$SRC/"
tar -czf "$TOPDIR/SOURCES/image-scrub-$VERSION.tar.gz" -C "build/rpm-src" "image-scrub-$VERSION"

rpmbuild -bb \
  --define "_topdir $(pwd)/$TOPDIR" \
  packaging/rpm/image-scrub.spec

echo "built $(find "$TOPDIR/RPMS" -name '*.rpm')"
