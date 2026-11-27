# Nix package for Image Scrub.
#
# Build with:  nix build
# Bundles the Pillow/PySide6/Flask/requests Python deps and wraps the CLIs.
{ lib, stdenv, python3, makeWrapper }:

let
  py = python3.withPackages (ps: [ ps.pillow ps.pyside6 ps.cbor2 ps.flask ps.requests ]);
in
stdenv.mkDerivation rec {
  pname = "image-scrub";
  version = "0.4.0";

  src = ./.;

  nativeBuildInputs = [ makeWrapper ];

  installPhase = ''
    runHook preInstall
    install -dm755 "$out/lib/image-scrub"
    cp -r image_scrub "$out/lib/image-scrub/image_scrub"
    cp cli_main.py desktop_gui.py webapp.py "$out/lib/image-scrub/"

    makeWrapper "${py}/bin/python3" "$out/bin/image-scrub" \
      --add-flags "$out/lib/image-scrub/cli_main.py"
    makeWrapper "${py}/bin/python3" "$out/bin/image-scrub-gui" \
      --add-flags "$out/lib/image-scrub/desktop_gui.py"

    install -Dm644 packaging/image-scrub.desktop \
      "$out/share/applications/image-scrub.desktop"
    install -Dm644 packaging/image-scrub.svg \
      "$out/share/icons/hicolor/scalable/apps/image-scrub.svg"
    for sz in 16 24 32 48 64 96 128 256 512; do
      install -Dm644 packaging/icons/hicolor/''${sz}x''${sz}/apps/image-scrub.png \
        "$out/share/icons/hicolor/''${sz}x''${sz}/apps/image-scrub.png"
    done
    runHook postInstall
  '';

  meta = with lib; {
    description = "Detect and strip provenance metadata (C2PA/EXIF/XMP/IPTC) from images";
    homepage = "https://github.com/VanguardArts/image-scrub";
    license = licenses.mit;
    mainProgram = "image-scrub";
    platforms = platforms.linux;
  };
}
