{
  inputs = {
    nixpkgs = {
      url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    };
    flake-utils = {
      url = "github:numtide/flake-utils";
    };

    cli-wrapper = {
      url = ./cli-wrapper;
      inputs = {
        nixpkgs.follows = "nixpkgs";
        flake-utils.follows = "flake-utils";
      };
    };
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    cli-wrapper,
    ...
  } @ inputs: let
    supported-systems = import ./targets.nix;
  in
    flake-utils.lib.eachSystem
    (builtins.attrNames supported-systems)
    (
      system: let
        pkgs = import nixpkgs {inherit system;};
        lib = nixpkgs.lib;
        python = pkgs.python312;

        cli-wrapper-pkgs = cli-wrapper.packages."${system}";
      in rec {
        packages = rec {
          inherit (cli-wrapper-pkgs) cargoArtifacts probe-cli;
          libprobe = pkgs.clangStdenv.mkDerivation rec {
            pname = "libprobe";
            version = "0.1.0";
            src = ./libprobe;
            makeFlags = [
              "INSTALL_PREFIX=$(out)"
              "SOURCE_VERSION=${version}"
            ];
            doCheck = true;
            checkInputs = [
              pkgs.clang-tools
              pkgs.cppcheck
              pkgs.include-what-you-use
            ];
            nativeBuildInputs = [
              pkgs.git
              (python.withPackages (pypkgs: [
                pypkgs.pycparser
                pypkgs.pyelftools
              ]))
            ];
            postUnpack = ''
              echo $src $sourceRoot $PWD
              mkdir $sourceRoot/generated
              cp ${probe-cli}/resources/bindings.h $sourceRoot/generated/
            '';
            VERSION = version;
            nativeCheckInputs = [
              pkgs.clang-analyzer
              pkgs.clang-tools
              pkgs.clang
              pkgs.compiledb
              pkgs.cppcheck
              pkgs.cppclean
            ];
            checkPhase = ''
              # make check
            '';
          };
          probe = pkgs.stdenv.mkDerivation rec {
            pname = "probe";
            version = "0.1.0";
            dontUnpack = true;
            dontBuild = true;
            nativeBuildInputs = [pkgs.makeWrapper];
            installPhase = ''
              mkdir $out $out/bin
              makeWrapper \
                ${cli-wrapper-pkgs.probe-cli}/bin/probe \
                $out/bin/probe \
                --set PROBE_LIB ${libprobe}/lib \
                --prefix PATH : ${python.withPackages (_: [probe-py])}/bin \
                --prefix PATH : ${pkgs.buildah}/bin
            '';
            passthru = {
              exePath = "/bin/probe";
            };
          };
          probe-py = python.pkgs.buildPythonPackage rec {
            pname = "probe_py";
            version = "0.1.0";
            pyproject = true;
            build-system = [
              python.pkgs.flit-core
            ];
            src = pkgs.stdenv.mkDerivation {
              src = ./probe_py;
              pname = "probe-py-with-pygen-code";
              version = "0.1.0";
              buildPhase = "true";
              installPhase = ''
                mkdir $out/
                cp --recursive $src/* $out/
                chmod 755 $out/probe_py
                cp ${probe-cli}/resources/ops.py $out/probe_py/
              '';
            };
            propagatedBuildInputs = [
              python.pkgs.networkx
              python.pkgs.pygraphviz
              python.pkgs.pydot
              python.pkgs.rich
              python.pkgs.typer
              python.pkgs.xdg-base-dirs
              python.pkgs.sqlalchemy
              python.pkgs.pyyaml
              python.pkgs.numpy
              python.pkgs.tqdm
            ];
            nativeCheckInputs = [
              python.pkgs.mypy
              python.pkgs.types-pyyaml
              python.pkgs.types-tqdm
              pkgs.ruff
            ];
            checkPhase = ''
              runHook preCheck
              #ruff format --check probe_src # TODO: uncomment
              ruff check .
              python -c 'import probe_py'
              MYPYPATH=$src/mypy_stubs:$MYPYPATH mypy --strict --package probe_py
              runHook postCheck
            '';
          };
          default = probe;
        };
        checks = {
          inherit
            (cli-wrapper.checks."${system}")
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
            buildPhase = "alejandra --check .";
          };
          probe-integration-tests = pkgs.stdenv.mkDerivation {
            name = "probe-integration-tests";
            src = ./tests;
            nativeBuildInputs =
              [
                packages.probe
                (python.withPackages (ps:
                  with ps; [
                    pytest
                    pytest-timeout
                    packages.probe-py
                  ]))
                pkgs.buildah
                pkgs.podman
                pkgs.docker
                pkgs.coreutils # so we can `probe record head ...`, etc.
                pkgs.gnumake
                pkgs.clang
              ]
              ++ pkgs.lib.lists.optional (system != "i686-linux" && system != "armv7l-linux") pkgs.jdk23_headless;
            buildPhase = ''
              make --directory=examples/
              export RUST_BAKCTRACE=1
              pytest -v -W error
            '';
            installPhase = "mkdir $out";
          };
        };
        apps = rec {
          default = probe;
          probe = flake-utils.lib.mkApp {
            drv = packages.probe;
          };
        };
        devShells = {
          default =
            (cli-wrapper.lib."${system}".craneLib.devShell.override {
              mkShell = pkgs.mkShellNoCC.override {
                stdenv = pkgs.clangStdenv;
              };
            }) {
              shellHook = ''
                export LIBCLANG_PATH="${pkgs.libclang.lib}/lib"
                pushd $(git rev-parse --show-toplevel) > /dev/null
                source ./setup_devshell.sh
                popd > /dev/null
              '';
              inputsFrom = [
                cli-wrapper-pkgs.probe-cli
              ];
              packages =
                [
                  (python.withPackages (pypkgs: [
                    # probe_py.manual runtime requirements
                    pypkgs.networkx
                    pypkgs.pydot
                    pypkgs.rich
                    pypkgs.typer
                    pypkgs.sqlalchemy
                    pypkgs.xdg-base-dirs
                    pypkgs.pyyaml
                    pypkgs.types-pyyaml
                    pypkgs.numpy
                    pypkgs.tqdm
                    pypkgs.types-tqdm

                    # probe_py.manual "dev time" requirements
                    pypkgs.psutil
                    pypkgs.pytest
                    pypkgs.pytest-timeout
                    pypkgs.mypy
                    pypkgs.ipython
                    pypkgs.xdg-base-dirs

                    # libprobe build time requirement
                    pypkgs.pycparser
                    pypkgs.pyelftools

                    # NOTE: a check-time input called "xvfb-run" is only available on linux
                    ((pypkgs.xdot.overrideAttrs (prev: {
                        checkPhase = null;
                        installCheckPhase = null;
                        nativeCheckInputs = [];
                      })).override {
                        xvfb-run = null;
                      })
                  ]))

                  # Replay tools
                  pkgs.buildah
                  pkgs.podman

                  # C tools
                  pkgs.clang-analyzer
                  pkgs.clang-tools # must go after clang-analyzer
                  pkgs.clang # must go after clang-tools
                  pkgs.cppcheck
                  pkgs.gnumake
                  pkgs.git
                  pkgs.include-what-you-use
                  pkgs.libclang
                  pkgs.criterion # unit testing framework

                  # rust tools
                  pkgs.cargo-deny
                  pkgs.cargo-audit
                  pkgs.cargo-machete
                  pkgs.cargo-hakari

                  pkgs.which
                  pkgs.coreutils
                  pkgs.alejandra
                  pkgs.just
                  pkgs.ruff
                ]
                # OpenJDK doesn't build on some platforms
                ++ pkgs.lib.lists.optional (system != "i686-linux" && system != "armv7l-linux") pkgs.nextflow
                ++ pkgs.lib.lists.optional (system != "i686-linux" && system != "armv7l-linux") pkgs.jdk23_headless
                # gdb broken on apple silicon
                ++ pkgs.lib.lists.optional (system != "aarch64-darwin") pkgs.gdb;
            };
        };
      }
    );
}
