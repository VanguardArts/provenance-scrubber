# Nix package for Provenance Scrubber.
#
# Build with:  nix build
# Bundles the Pillow/PySide6/Flask/requests Python deps and wraps the CLIs.
{ lib, stdenv, python3, makeWrapper }:

let
  py = python3.withPackages (ps: [ ps.pillow ps.pyside6 ps.cbor2 ps.flask ps.requests ]);
in
stdenv.mkDerivation rec {
  pname = "provenance-scrubber";
  version = "0.3.1";

  src = ./.;

  nativeBuildInputs = [ makeWrapper ];

  installPhase = ''
    runHook preInstall
    install -dm755 "$out/lib/provenance-scrubber"
    cp -r scrubber "$out/lib/provenance-scrubber/scrubber"
    cp cli_main.py desktop_gui.py webapp.py "$out/lib/provenance-scrubber/"

    makeWrapper "${py}/bin/python3" "$out/bin/provenance-scrubber" \
      --add-flags "$out/lib/provenance-scrubber/cli_main.py"
    makeWrapper "${py}/bin/python3" "$out/bin/provenance-scrubber-gui" \
      --add-flags "$out/lib/provenance-scrubber/desktop_gui.py"

    install -Dm644 packaging/provenance-scrubber.desktop \
      "$out/share/applications/provenance-scrubber.desktop"
    install -Dm644 packaging/provenance-scrubber.svg \
      "$out/share/icons/hicolor/scalable/apps/provenance-scrubber.svg"
    for sz in 16 24 32 48 64 96 128 256 512; do
      install -Dm644 packaging/icons/hicolor/''${sz}x''${sz}/apps/provenance-scrubber.png \
        "$out/share/icons/hicolor/''${sz}x''${sz}/apps/provenance-scrubber.png"
    done
    runHook postInstall
  '';

  meta = with lib; {
    description = "Detect and strip provenance metadata (C2PA/EXIF/XMP/IPTC) from images";
    homepage = "https://github.com/VanguardArts/provenance-scrubber";
    license = licenses.mit;
    mainProgram = "provenance-scrubber";
    platforms = platforms.linux;
  };
}
