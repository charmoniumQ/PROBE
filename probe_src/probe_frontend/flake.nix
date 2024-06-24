{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    crane.url = "github:ipetkov/crane";
    crane.inputs.nixpkgs.follows = "nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    crane,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      craneLib = crane.mkLib pkgs;

      crate = craneLib.buildPackage {
        src = ./.;

        # Add extra inputs here or any other derivation settings
        doCheck = true;
        # buildInputs = [];
        nativeBuildInputs = [
          pkgs.rustPlatform.bindgenHook
        ];
      };
    in {
      packages.default = crate;
      checks = {
        inherit crate;
      };
      devShells.default = craneLib.devShell {
        checks = self.checks.${system};
        packages = with pkgs; [
          rust-analyzer
          cargo-audit
        ];
      };
    });
}
