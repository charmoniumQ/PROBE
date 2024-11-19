{
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

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    rust-overlay,
    crane,
    advisory-db,
    ...
  } @ inputs: let
    supported-systems = {
      # "nix system" = "rust target";
      "x86_64-linux" = "x86_64-unknown-linux-musl";
      # Even with Nextflow (requires OpenJDK) removed,
      # i686-linux still doesn't build.
      # Only the wind and water know why. Us mere mortals never will.
      #"i686-linux" = "i686-unknown-linux-musl";
      "aarch64-linux" = "aarch64-unknown-linux-musl";
      "armv7l-linux" = "armv7-unknown-linux-musleabi";
    };
  in
    flake-utils.lib.eachSystem
    (builtins.attrNames supported-systems)
    (
      system: let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [(import rust-overlay)];
        };
        lib = nixpkgs.lib;
        python = pkgs.python312;
        rust-target = supported-systems.${system};
        craneLib = (crane.mkLib pkgs).overrideToolchain (p:
          p.rust-bin.stable.latest.default.override {
            targets = [rust-target];
          });
        frontend = (import ./probe_src/frontend/frontend.nix) {
          inherit
            system
            pkgs
            python
            rust-target
            craneLib
            lib
            advisory-db
            ;
        };
      in rec {
        packages = rec {
          inherit (frontend.packages) cargoArtifacts;
          libprobe = pkgs.stdenv.mkDerivation rec {
            pname = "libprobe";
            version = "0.1.0";
            src = ./probe_src/libprobe;
            makeFlags = ["INSTALL_PREFIX=$(out)" "SOURCE_VERSION=${version}"];
            buildInputs = [
              (pkgs.python312.withPackages (pypkgs: [
                pypkgs.pycparser
              ]))
            ];
          };
          probe-bundled = pkgs.stdenv.mkDerivation rec {
            pname = "probe-bundled";
            version = "0.1.0";
            dontUnpack = true;
            dontBuild = true;
            nativeBuildInputs = [pkgs.makeWrapper];
            installPhase = ''
              mkdir $out $out/bin
              makeWrapper \
                ${frontend.packages.probe-cli}/bin/probe \
                $out/bin/probe \
                --set __PROBE_LIB ${libprobe}/lib \
                --prefix PATH : ${probe-py}/bin \
                --prefix PATH : ${pkgs.buildah}/bin
            '';
          };
          probe-py-generated = frontend.packages.probe-py-generated;
          probe-py = let
            probe-py-manual = python.pkgs.buildPythonPackage rec {
              pname = "probe_py.manual";
              version = "0.1.0";
              pyproject = true;
              build-system = [
                python.pkgs.flit-core
              ];
              src = ./probe_src/python;
              propagatedBuildInputs = [
                frontend.packages.probe-py-generated
                python.pkgs.networkx
                python.pkgs.pygraphviz
                python.pkgs.pydot
                python.pkgs.rich
                python.pkgs.typer
                python.pkgs.sqlalchemy
                python.pkgs.xdg-base-dirs
              ];
              nativeCheckInputs = [
                frontend.packages.probe-py-generated
                python.pkgs.mypy
                pkgs.ruff
              ];
              checkPhase = ''
                runHook preCheck
                #ruff format --check probe_src # TODO: uncomment
                ruff check .
                python -c 'import probe_py.manual'
                mypy --strict --package probe_py.manual
                runHook postCheck
              '';
            };
          in
            python.withPackages (pypkgs: [probe-py-manual]);
          default = probe-bundled;
        };
        checks = {
          inherit
            (frontend.checks)
            probe-workspace-clippy
            probe-workspace-doc
            probe-workspace-fmt
            probe-workspace-audit
            probe-workspace-deny
            probe-workspace-nextest
            ;
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
              pushd $(git rev-parse --show-toplevel)
              source ./setup_devshell.sh
              popd
            '';
            inputsFrom = [
              frontend.packages.probe-frontend
              frontend.packages.probe-cli
              frontend.packages.probe-macros
            ];
            packages =
              [
                pkgs.cargo-audit
                pkgs.cargo-expand
                pkgs.cargo-flamegraph
                pkgs.cargo-watch
                pkgs.rust-analyzer

                (python.withPackages (pypkgs: [
                  # probe_py.manual runtime requirements
                  pypkgs.networkx
                  pypkgs.pygraphviz
                  pypkgs.pydot
                  pypkgs.rich
                  pypkgs.typer
                  pypkgs.sqlalchemy
                  pypkgs.xdg-base-dirs

                  # probe_py.manual "dev time" requirements
                  pypkgs.psutil
                  pypkgs.pytest
                  pypkgs.mypy
                  pypkgs.ipython

                  # libprobe build time requirement
                  pypkgs.pycparser
                ]))

                # (export-and-rename python312-debug [["bin/python" "bin/python-dbg"]])

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
                pkgs.jq # to make cachix work
                pkgs.podman
              ]
              # gdb broken on i686
              ++ pkgs.lib.lists.optional (system != "i686-linux") pkgs.nextflow
              # gdb broken on apple silicon
              ++ pkgs.lib.lists.optional (system != "aarch64-darwin") pkgs.gdb
              # while xdot isn't marked as linux only, it has a dependency (xvfb-run) that is
              ++ pkgs.lib.lists.optional (builtins.elem system pkgs.lib.platforms.linux) pkgs.xdot;
          };
        };
      }
    );
}
