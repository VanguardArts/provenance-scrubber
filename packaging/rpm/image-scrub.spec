Name:           image-scrub
Version:        0.4.0
Release:        1%{?dist}
Summary:        Detect and strip provenance metadata (C2PA/EXIF/XMP/IPTC) from images
License:        MIT
URL:            https://github.com/VanguardArts/image-scrub
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
# python3-pillow (Fedora) vs python3-pil (Debian); PySide6 = python3-pyside6.
Requires:       python3
Requires:       python3-pillow
Requires:       python3-pyside6
Requires:       python3-cbor2

%description
Batches images and removes embedded provenance signals — C2PA Content
Credentials manifests, EXIF, XMP, IPTC and generator strings — with optional
pixel-domain transforms that degrade invisible watermarks. Ships the
image-scrub CLI and the image-scrub-gui desktop app.

%prep
%autosetup

%build
# nothing to compile — pure Python

%install
LIBDIR=%{buildroot}%{_prefix}/lib/image-scrub
mkdir -p "$LIBDIR" %{buildroot}%{_bindir} \
         %{buildroot}%{_datadir}/applications \
         %{buildroot}%{_datadir}/icons/hicolor/scalable/apps

cp -r image_scrub "$LIBDIR/image_scrub"
cp cli_main.py desktop_gui.py webapp.py "$LIBDIR/"

printf '#!/bin/sh\nexec python3 %{_prefix}/lib/image-scrub/cli_main.py "$@"\n' \
    > %{buildroot}%{_bindir}/image-scrub
printf '#!/bin/sh\nexec python3 %{_prefix}/lib/image-scrub/desktop_gui.py "$@"\n' \
    > %{buildroot}%{_bindir}/image-scrub-gui
chmod 755 %{buildroot}%{_bindir}/image-scrub \
          %{buildroot}%{_bindir}/image-scrub-gui

install -m 644 packaging/image-scrub.desktop \
    %{buildroot}%{_datadir}/applications/image-scrub.desktop
install -m 644 packaging/image-scrub.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/image-scrub.svg
for sz in 16 24 32 48 64 96 128 256 512; do
  install -Dm 644 "packaging/icons/hicolor/${sz}x${sz}/apps/image-scrub.png" \
      "%{buildroot}%{_datadir}/icons/hicolor/${sz}x${sz}/apps/image-scrub.png"
done

%files
%{_bindir}/image-scrub
%{_bindir}/image-scrub-gui
%{_prefix}/lib/image-scrub/
%{_datadir}/applications/image-scrub.desktop
%{_datadir}/icons/hicolor/scalable/apps/image-scrub.svg
%{_datadir}/icons/hicolor/16x16/apps/image-scrub.png
%{_datadir}/icons/hicolor/24x24/apps/image-scrub.png
%{_datadir}/icons/hicolor/32x32/apps/image-scrub.png
%{_datadir}/icons/hicolor/48x48/apps/image-scrub.png
%{_datadir}/icons/hicolor/64x64/apps/image-scrub.png
%{_datadir}/icons/hicolor/96x96/apps/image-scrub.png
%{_datadir}/icons/hicolor/128x128/apps/image-scrub.png
%{_datadir}/icons/hicolor/256x256/apps/image-scrub.png
%{_datadir}/icons/hicolor/512x512/apps/image-scrub.png

%changelog
* Sun Nov 22 2026 Vanguard Arts SRL <https://vanguardarts.vip/> - 0.4.0-1
- Detector plugins: OpenAI Content Provenance API (C2PA + SynthID) and
  Meta Stable Signature pixel-watermark decoder; optional c2pa-python
  cryptographic verification in the analyzer
* Sun Nov 22 2026 Vanguard Arts SRL <https://vanguardarts.vip/> - 0.3.1-1
- Update GUI detail pane and regenerate screenshots
* Sun Nov 22 2026 Vanguard Arts SRL <https://vanguardarts.vip/> - 0.3.0-1
- Add provenance analyzer/viewer with before/after diff
* Sat Nov 21 2026 Vanguard Arts SRL <https://vanguardarts.vip/> - 0.2.0-1
- Linux packaging: deb, rpm, PKGBUILD, nix, flatpak, AppImage
* Sat Nov 21 2026 Vanguard Arts SRL <https://vanguardarts.vip/> - 0.1.0-1
- Initial RPM packaging
