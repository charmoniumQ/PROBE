{
  inputs = {
    nixpkgs.url = "nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    fenix.url = "github:nix-community/fenix";
    fenix.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, flake-utils, fenix }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python310;
        noPytest = pypkg: pypkg.overrideAttrs (self: super: {
          pytestCheckPhase = ''true'';
        });
        rust = fenix.packages.x86_64-linux.default.toolchain;
      in
      {
        packages = rec {
          prov-tracer = pkgs.rustPlatform.buildRustPackage {
            pname = "libc-prov-tracer";
            version = "0.1.0";
            cargoLock = {
              lockFile = ./Cargo.lock;
            };
          };
          default = prov-tracer;
        };
        devShells = {
          default = pkgs.mkShell {
            packages = [ rust ];
          };
        };
        apps = rec {
          cargo = {
            type = "app";
            program = let
              package = pkgs.writeShellScriptBin "script" ''
                ${rust}/bin/cargo "$@"
              '';
            in "${package}/bin/script";
          };
          build = {
            type = "app";
            program = let
              package = pkgs.writeShellScriptBin "script" ''
                ${rust}/bin/cargo build "$@"
              '';
            in "${package}/bin/script";
          };
        };
      }
    )
  ;
}
