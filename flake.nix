{
  description = "Image Scrub — detect and strip provenance metadata from images";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        packages.default = pkgs.callPackage ./default.nix { };
        packages.image-scrub = self.packages.${system}.default;
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/image-scrub";
        };
      });
}
