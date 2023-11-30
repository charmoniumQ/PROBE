{
  inputs.flake-utils.url = "github:numtide/flake-utils";
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python310;
        noPytest = pypkg: pypkg.overrideAttrs (self: super: {
          pytestCheckPhase = ''true'';
        });
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
            packages = [ pkgs.cargo pkgs.rustc ];
          };
        };
        apps = {
          cargo = {
            type = "app";
            program = let
              package = pkgs.writeShellScriptBin "script" ''
                ${pkgs.cargo}/bin/cargo "$@"
              '';
            in "${package}/bin/script";
          };
          build = {
            type = "app";
            program = let
              package = pkgs.writeShellScriptBin "script" ''
                ${pkgs.cargo}/bin/cargo build "$@"
              '';
            in "${package}/bin/script";
          };
        };
      }
    )
  ;
}
