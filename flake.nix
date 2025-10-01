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
    probe-ver = "0.0.10";
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
          charmonium-freeze = python.pkgs.buildPythonPackage rec {
            pname = "charmonium_freeze";
            version = "0.8.6";
            format = "pyproject";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "4bc1e976dbdc668eab295d5a709db09c0372690b339f49d0d20c4f5ab8104c65";
            };
            propagatedBuildInputs = [
              python.pkgs.typing-extensions
            ];
            buildInputs = [
              python.pkgs.hatchling
            ];
            pythonImportsCheck = [ "charmonium.freeze" ];
          };
          charmonium-cache = python.pkgs.buildPythonPackage rec {
            pname = "charmonium_cache";
            version = "1.4.1";
            format = "pyproject";
            propagatedBuildInputs = [
              charmonium-freeze
              python.pkgs.bitmath
              python.pkgs.fasteners
            ];
            buildInputs = [
              python.pkgs.poetry-core
            ];
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "f299b7a488877af2622fc261bf54a6e8807532e017b892b7b00b21c328ec214c";
            };
            pythonImportsCheck = [ "charmonium.cache" ];
          };
          inherit (cli-wrapper-pkgs) cargoArtifacts probe-cli;
          libprobe = pkgs.clangStdenv.mkDerivation rec {
            pname = "libprobe";
            version = probe-ver;
            src = ./libprobe;
            makeFlags = [
              "INSTALL_PREFIX=$(out)"
              "SOURCE_VERSION=${version}"
            ];
            doCheck = true;
            checkInputs = [
              pkgs.clang-tools
              pkgs.cppcheck
              pkgs.criterion
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
              SKIP_IWYU=1 SKIP_CHECK_NEEDED_SYMS=1 make check
            '';
          };
          probe = pkgs.stdenv.mkDerivation rec {
            pname = "probe";
            version = probe-ver;
            dontUnpack = true;
            dontBuild = true;
            nativeBuildInputs = [pkgs.makeWrapper];
            installPhase = ''
              mkdir $out $out/bin
              makeWrapper \
                ${cli-wrapper-pkgs.probe-cli}/bin/probe \
                $out/bin/probe \
                --set PROBE_LIB ${libprobe}/lib \
                --prefix PATH_TO_PROBE_PYTHON : ${python.withPackages (_: [probe-py])}/bin/python \
                --prefix PATH_TO_BUILDAH : ${pkgs.buildah}/bin/buildah
            '';
            passthru = {
              exePath = "/bin/probe";
            };
          };
          probe-py = python.pkgs.buildPythonPackage rec {
            pname = "probe_py";
            version = probe-ver;
            pyproject = true;
            build-system = [
              python.pkgs.flit-core
            ];
            src = pkgs.stdenv.mkDerivation {
              src = ./probe_py;
              pname = "probe-py-with-pygen-code";
              version = probe-ver;
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
          docker-image = pkgs.dockerTools.buildImage {
            # nix build .#docker-image && podman load < result
            name = "probe";
            tag = probe-ver;
            copyToRoot = pkgs.buildEnv {
              name = "probe-sys-env";
              paths = [
                probe
                pkgs.busybox
              ];
              pathsToLink = ["/bin"];
            };
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
                  # Rust tools
                  pkgs.cargo-deny
                  pkgs.cargo-audit
                  pkgs.cargo-machete
                  pkgs.cargo-hakari

                  (python.withPackages (pypkgs: [
                    # probe_py.manual runtime requirements
                    pypkgs.networkx
                    pypkgs.pydot
                    pypkgs.rich
                    pypkgs.typer
                    pypkgs.sqlalchemy
                    pypkgs.xdg-base-dirs
                    pypkgs.pyyaml
                    pypkgs.numpy
                    pypkgs.tqdm

                    # probe_py.manual "dev time" requirements
                    pypkgs.types-tqdm
                    pypkgs.types-pyyaml
                    pypkgs.pytest
                    pypkgs.pytest-timeout
                    pypkgs.mypy
                    pypkgs.ipython

                    # benchmark/papers-with-code requirements
                    pypkgs.aioconsole
                    pypkgs.githubkit
                    pypkgs.httpx
                    pypkgs.huggingface-hub
                    pypkgs.matplotlib
                    pypkgs.polars
                    pypkgs.pydantic
                    pypkgs.pydantic-yaml
                    pypkgs.seaborn
                    pypkgs.tqdm
                    pypkgs.typer
                    pypkgs.yarl
                    pypkgs.ipython
                    pypkgs.typing-extensions
                    packages.charmonium-cache

                    # libprobe build time requirement
                    pypkgs.pycparser
                    pypkgs.pyelftools
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

                  pkgs.ty
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
