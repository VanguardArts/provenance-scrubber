#!/usr/bin/env bash
# Build a noarch .rpm for provenance-scrubber.
# Needs: rpmbuild (and a source tarball named provenance-scrubber-<ver>.tar.gz).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.2.0}"
TOPDIR="build/rpm"

rm -rf "$TOPDIR"
mkdir -p "$TOPDIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# make a clean source tarball with the required top-level dir
SRC="build/rpm-src/provenance-scrubber-$VERSION"
rm -rf "build/rpm-src"
mkdir -p "$SRC"
cp -r scrubber cli_main.py desktop_gui.py webapp.py packaging LICENSE README.md "$SRC/"
tar -czf "$TOPDIR/SOURCES/provenance-scrubber-$VERSION.tar.gz" -C "build/rpm-src" "provenance-scrubber-$VERSION"

rpmbuild -bb \
  --define "_topdir $(pwd)/$TOPDIR" \
  packaging/rpm/provenance-scrubber.spec

echo "built $(find "$TOPDIR/RPMS" -name '*.rpm')"
