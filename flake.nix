{
  description = "Probe Project Flake";

  inputs = {
    nixpkgs = {
      url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    };
    flake-utils = {
      url = "github:numtide/flake-utils";
    };
    crane = {
      url = "github:ipetkov/crane";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    advisory-db = {
      url = "github:rustsec/advisory-db";
      flake = false;
    };
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, rust-overlay, crane, advisory-db, ... }:
  let
    supportedSystems = {
      "x86_64-linux" = "x86_64-unknown-linux-musl";
      "aarch64-linux" = "aarch64-unknown-linux-musl";
      "armv7l-linux" = "armv7-unknown-linux-musleabi";
      "aarch64-darwin" = "aarch64-apple-darwin"; # Added macOS support
      "x86_64-darwin" = "x86_64-apple-darwin";
    };
  in
  flake-utils.lib.eachSystem (builtins.attrNames supportedSystems) (system:
    let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [
          (import rust-overlay)
        ];
      };
      lib = pkgs.lib;
      python = pkgs.python312;
      pythonPackages = pkgs.python312Packages;
      rustTarget = supportedSystems.${system};
      craneLib = (crane.mkLib pkgs).overrideToolchain (p:
        p.rust-bin.stable.latest.default.override {
          targets = [rustTarget];
        });

      # Define SDK paths and frameworks for macOS
      sdkroot = if pkgs.stdenv.isDarwin then "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk" else null;
      frameworkPath = if pkgs.stdenv.isDarwin then "${sdkroot}/System/Library/Frameworks" else null;

      # Define frameworks manually
      frameworks = if pkgs.stdenv.isDarwin then {
        IOKit = "${frameworkPath}/IOKit.framework";
        CoreFoundation = "${frameworkPath}/CoreFoundation.framework";
      } else {};

      frontend = (import ./probe_src/frontend/frontend.nix) {
        inherit system pkgs python craneLib lib advisory-db;
        rust-target = rustTarget;
      };
    in
    rec {
      packages = rec {
        inherit (frontend.packages) cargoArtifacts;

        libprobe = pkgs.stdenv.mkDerivation rec {
          pname = "libprobe";
          version = "0.1.0";
          src = ./probe_src/libprobe;
          makeFlags = [
            "INSTALL_PREFIX=$(out)"
            "SOURCE_VERSION=${version}"
          ];
          buildInputs = [
            (python.withPackages (pypkgs: [pypkgs.pycparser]))
            pkgs.gcc
          ] ++ lib.optional (pkgs.stdenv.isDarwin) [
            frameworks.IOKit
            frameworks.CoreFoundation
          ];
          nativeBuildInputs = [pkgs.pkg-config];

          # Set environment variables for macOS
          NIX_CFLAGS_COMPILE = lib.optionalString (pkgs.stdenv.isDarwin) ''
            -isysroot ${sdkroot} -F${frameworkPath}
          '';
          NIX_LDFLAGS = lib.optionalString (pkgs.stdenv.isDarwin) ''
            -F${frameworkPath}
          '';

          # Use system clang for macOS
preConfigure = lib.optionalString (pkgs.stdenv.isDarwin) ''
  export CC=${pkgs.gcc}/bin/gcc
  export CXX=${pkgs.gcc}/bin/g++
'';

        };

        probe-bundled = pkgs.stdenv.mkDerivation rec {
          pname = "probe-bundled";
          version = "0.1.0";
          dontUnpack = true;
          dontBuild = true;
          nativeBuildInputs = [pkgs.makeWrapper];
          installPhase = ''
            mkdir -p $out/bin
            makeWrapper \
              ${frontend.packages.probe-cli}/bin/probe \
              $out/bin/probe \
              --set __PROBE_LIB ${libprobe}/lib \
              --prefix PATH : ${packages.probe-py}/bin \
              --prefix PATH : ${pkgs.buildah}/bin
          '';
        };

        probe-py-generated = frontend.packages.probe-py-generated;

        probe-py = let
          probePyManual = pythonPackages.buildPythonPackage rec {
            pname = "probe_py.manual";
            version = "0.1.0";
            pyproject = true;
            buildSystems = ["flit-core"];
            src = ./probe_src/python;
            propagatedBuildInputs = [
              frontend.packages.probe-py-generated
              pythonPackages.networkx
              pythonPackages.pygraphviz
              pythonPackages.pydot
              pythonPackages.rich
              pythonPackages.typer
            ];
            nativeCheckInputs = [
              frontend.packages.probe-py-generated
              pythonPackages.mypy
              pkgs.ruff
            ];
            checkPhase = ''
              runHook preCheck
              ruff check .
              python -c 'import probe_py.manual'
              mypy --strict --package probe_py.manual
              runHook postCheck
            '';
          };
        in
          probePyManual;

        default = probe-bundled;
      };

      checks = {
        inherit (frontend.checks) probe-workspace-clippy probe-workspace-doc probe-workspace-fmt probe-workspace-audit probe-workspace-deny probe-workspace-nextest;

        fmt-nix = pkgs.stdenv.mkDerivation {
          name = "fmt-nix";
          src = ./.;
          doCheck = true;
          nativeBuildInputs = [pkgs.alejandra];
          installPhase = "mkdir $out";
          buildPhase = "true";
          checkPhase = ''
            alejandra --check .
          '';
        };

        probe-integration-tests = pkgs.stdenv.mkDerivation {
          name = "probe-integration-tests";
          src = ./probe_src/tests;
          nativeBuildInputs = [
            packages.probe-bundled
            packages.probe-py
            pkgs.podman
            pkgs.docker
          ];
          buildPhase = "touch $out";
          checkPhase = ''
            pytest .
          '';
        };
      };

      devShells = {
        default = craneLib.devShell {
          shellHook = ''
            if [[ "$(uname)" == "Darwin" ]]; then
              export SDKROOT=${sdkroot}
              export NIX_LDFLAGS="-F${frameworkPath} $NIX_LDFLAGS"
            fi
            pushd $(git rev-parse --show-toplevel)
            source ./setup_devshell.sh
            popd
          '';
          inputsFrom = [
            frontend.packages.probe-frontend
            frontend.packages.probe-cli
            frontend.packages.probe-macros
          ];
          packages = [
            pkgs.cargo-audit
            pkgs.cargo-expand
            pkgs.cargo-flamegraph
            pkgs.cargo-watch
            pkgs.rust-analyzer
            (python.withPackages (pypkgs: [
              pythonPackages.networkx
              pythonPackages.pygraphviz
              pythonPackages.pydot
              pythonPackages.rich
              pythonPackages.typer
              pythonPackages.psutil
              pythonPackages.pytest
              pythonPackages.mypy
              pythonPackages.ipython
              pythonPackages.pycparser
            ]))
            pkgs.buildah
            pkgs.which
            pkgs.gnumake
            pkgs.gcc
            pkgs.coreutils
            pkgs.bash
            pkgs.alejandra
            pkgs.hyperfine
            pkgs.just
            pkgs.ruff
            pkgs.cachix
            pkgs.jq
            pkgs.podman
          ] ++ lib.optional (system != "i686-linux") pkgs.nextflow
            ++ lib.optional (system != "aarch64-darwin") pkgs.gdb
            ++ lib.optional (builtins.elem system pkgs.lib.platforms.linux) pkgs.xdot
            ++ lib.optional (pkgs.stdenv.isDarwin) [
              frameworks.IOKit
              frameworks.CoreFoundation
            ];
        };
      };
    });
}
