Name:           provenance-scrubber
Version:        0.1.0
Release:        1%{?dist}
Summary:        Detect and strip provenance metadata (C2PA/EXIF/XMP/IPTC) from images
License:        MIT
URL:            https://github.com/VanguardArts/provenance-scrubber
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
# python3-pillow (Fedora) vs python3-pil (Debian); PySide6 = python3-pyside6.
Requires:       python3
Requires:       python3-pillow
Requires:       python3-pyside6

%description
Batches images and removes embedded provenance signals — C2PA Content
Credentials manifests, EXIF, XMP, IPTC and generator strings — with optional
pixel-domain transforms that degrade invisible watermarks. Ships the
provenance-scrubber CLI and the provenance-scrubber-gui desktop app.

%prep
%autosetup

%build
# nothing to compile — pure Python

%install
LIBDIR=%{buildroot}%{_prefix}/lib/provenance-scrubber
mkdir -p "$LIBDIR" %{buildroot}%{_bindir} \
         %{buildroot}%{_datadir}/applications \
         %{buildroot}%{_datadir}/icons/hicolor/scalable/apps

cp -r scrubber "$LIBDIR/scrubber"
cp cli_main.py desktop_gui.py webapp.py "$LIBDIR/"

printf '#!/bin/sh\nexec python3 %{_prefix}/lib/provenance-scrubber/cli_main.py "$@"\n' \
    > %{buildroot}%{_bindir}/provenance-scrubber
printf '#!/bin/sh\nexec python3 %{_prefix}/lib/provenance-scrubber/desktop_gui.py "$@"\n' \
    > %{buildroot}%{_bindir}/provenance-scrubber-gui
chmod 755 %{buildroot}%{_bindir}/provenance-scrubber \
          %{buildroot}%{_bindir}/provenance-scrubber-gui

install -m 644 packaging/provenance-scrubber.desktop \
    %{buildroot}%{_datadir}/applications/provenance-scrubber.desktop
install -m 644 packaging/provenance-scrubber.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/provenance-scrubber.svg
for sz in 16 24 32 48 64 96 128 256 512; do
  install -Dm 644 "packaging/icons/hicolor/${sz}x${sz}/apps/provenance-scrubber.png" \
      "%{buildroot}%{_datadir}/icons/hicolor/${sz}x${sz}/apps/provenance-scrubber.png"
done

%files
%{_bindir}/provenance-scrubber
%{_bindir}/provenance-scrubber-gui
%{_prefix}/lib/provenance-scrubber/
%{_datadir}/applications/provenance-scrubber.desktop
%{_datadir}/icons/hicolor/scalable/apps/provenance-scrubber.svg
%{_datadir}/icons/hicolor/16x16/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/24x24/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/32x32/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/48x48/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/64x64/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/96x96/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/128x128/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/256x256/apps/provenance-scrubber.png
%{_datadir}/icons/hicolor/512x512/apps/provenance-scrubber.png

%changelog
* Sat Nov 21 2026 Vanguard Arts SRL <https://vanguardarts.vip/> - 0.1.0-1
- Initial RPM packaging (noarch, pure Python).
