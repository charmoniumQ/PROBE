{
  inputs = {
    nixpkgs = {
      url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    };
    old-nixpkgs = {
      # https://lazamar.co.uk/nix-versions/?channel=nixpkgs-unstable&package=glibc
      # See PROBE/docs/old-glibc.md
      # glibc = 2.33
      url = "github:NixOS/nixpkgs/d1c3fea7ecbed758168787fe4e4a3157e52bc808";
      # If pulling nixpkgs from 2020 or older, need to set flake = false.
      flake = false;
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
    old-nixpkgs,
    flake-utils,
    cli-wrapper,
    ...
  } @ inputs: let
    supported-systems = import ./targets.nix;
    probe-ver = "0.0.13";
  in
    flake-utils.lib.eachSystem
    (builtins.attrNames supported-systems)
    (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        cli-wrapper-pkgs = cli-wrapper.packages.${system};
        # IF flake = false, we need to do this instead
        old-pkgs = import old-nixpkgs {inherit system;};
        # Otherwise, if old-nixpkgs is a flake,
        #old-pkgs = old-nixpkgs.legacyPackages.${system};
        new-clang-old-glibc = pkgs.wrapCCWith {
          cc = pkgs.clang;
          bintools = pkgs.wrapBintoolsWith {
            inherit (pkgs) bintools;
            libc = old-pkgs.glibc;
          };
        };
        old-stdenv = pkgs.overrideCC pkgs.stdenv new-clang-old-glibc;
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
            pythonImportsCheck = ["charmonium.freeze"];
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
            pythonImportsCheck = ["charmonium.cache"];
          };
          inherit (cli-wrapper-pkgs) cargoArtifacts probe-cli;
          libprobe = old-stdenv.mkDerivation rec {
            pname = "libprobe";
            name = "${pname}-${version}";
            version = probe-ver;
            src = ./libprobe;
            makeFlags = [
              "INSTALL_PREFIX=$(out)"
              "SOURCE_VERSION=v${version}"
              # Somehow, old-stdenv is not enough.
              # I must not be overriding it correctly.
              # Explicitly set CC instead.
              "CC=${new-clang-old-glibc}/bin/cc"
            ];
            doCheck = true;
            nativeCheckInputs = [
              old-pkgs.criterion
              pkgs.include-what-you-use
              pkgs.clang-analyzer
              pkgs.clang-tools
              pkgs.clang
              pkgs.compiledb
              pkgs.cppcheck
              pkgs.cppclean
            ];
            checkPhase = ''
              # When a user buidls this WITHOUT build sandbox isolation, the libc files appear to come from somewhere different.
              # For some reason, this confuses the `IWYU pragma: no_include`, causing an IWYU failure.
              # So I will disable the check here.
              # It is still enabled in the Justfile, and still works in the devshell.
              export SKIP_IWYU=1

              # Probably because I am explicitly setting CC, the unittests are not compatible with the Nix sandbox.
              #
              #     .build/probe_libc_tests: /nix/store/qhw0sp183mqd04x5jp75981kwya64npv-glibc-2.40-66/lib/libpthread.so.0: version `GLIBC_PRIVATE' not found (required by /nix/store/q29bwjibv9gi9n86203s38n0577w09sx-glibc-2.33-117/lib/librt.so.1)
              #     .build/probe_libc_tests: /nix/store/qhw0sp183mqd04x5jp75981kwya64npv-glibc-2.40-66/lib/libpthread.so.0: version `GLIBC_PRIVATE' not found (required by /nix/store/q29bwjibv9gi9n86203s38n0577w09sx-glibc-2.33-117/lib/libanl.so.1)
              #
              # Unittests are still checked in the Justfile and still work in the  devshell.
              export SKIP_UNITTESTS=1

              make check
            '';
            nativeBuildInputs = [
              pkgs.git
              (python.withPackages (pypkgs: [
                pypkgs.pycparser
                pypkgs.pyelftools
              ]))
            ];
            postUnpack = ''
              mkdir $sourceRoot/generated
              cp ${probe-cli}/resources/bindings.h $sourceRoot/generated/
            '';
            VERSION = version;
          };
          probe = pkgs.stdenv.mkDerivation rec {
            pname = "probe";
            version = probe-ver;
            dontUnpack = true;
            dontBuild = true;
            nativeBuildInputs = [pkgs.makeWrapper];
            installPhase = ''
              mkdir $out $out/bin
              # We don't want to add these to the PATH and PYTHONPATH because that will have side-effects on the target of `probe record`.
              makeWrapper \
                ${cli-wrapper-pkgs.probe-cli}/bin/probe \
                $out/bin/probe \
                --set PROBE_BUILDAH ${pkgs.buildah}/bin/buildah \
                --set PROBE_LIB ${libprobe}/lib \
                --set PROBE_PYTHON ${python.withPackages (_: [probe-py])}/bin/python \
                --set PROBE_PYTHONPATH ""
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
            name = "probe";
            tag = probe-ver;
            copyToRoot = pkgs.buildEnv {
              name = "probe-sys-env";
              paths = [probe];
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
        devShells = let
          probe-python = python.withPackages (pypkgs: [
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
          ]);
          shellHook = ''
            #export LIBCLANG_PATH="$old-pkgs.libclang.lib}/lib"
            export PROBE_BUILDAH="${pkgs.buildah}/bin/buildah"
            export PROBE_PYTHON="${probe-python}/bin/python"
            pushd $(git rev-parse --show-toplevel) > /dev/null
            source ./setup_devshell.sh
            popd > /dev/null
          '';
          shellPackages =
            [
              # Rust tools
              pkgs.cargo-deny
              pkgs.cargo-audit
              pkgs.cargo-machete
              pkgs.cargo-hakari

              # Replay tools
              pkgs.buildah
              pkgs.podman

              # C tools
              pkgs.clang-analyzer
              pkgs.clang-tools # must go after clang-analyzer
              pkgs.cppcheck
              pkgs.gnumake
              pkgs.git
              pkgs.include-what-you-use
              old-pkgs.criterion # unit testing framework

              probe-python
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
        in rec {
          # Instead, we use the new stdenv while explictly setting $CC.
          # At runtime, programs, including libprobe, sees the new CC.
          # As Glibc maintains backwards compatibility, "compile with old and run with new" should work.
          # We have this because the Crane devshell changes some stuff, so we want to have a non-Crane devshell.
          # Currently, it seems that the Crane one works though.
          old-cc = pkgs.mkShell {
            shellHook =
              ''
                export CC=${old-stdenv.cc}/bin/cc
              ''
              + shellHook;
            packages = shellPackages;
          };

          # And instead of that, we use Crane's take on this.
          # We used to override Crane's mkShell's stdenv,
          #
          #     (craneLib.devShell.override {
          #       mkShell = pkgs.mkShell.override { stdenv = pkgs.clangStdenv; };
          #     }) { ... }
          #
          # But now that we explicitly set $CC in the shell hook, no need.
          crane-old-cc = cli-wrapper.lib."${system}".craneLib.devShell {
            inputsFrom = [
              cli-wrapper-pkgs.probe-cli
            ];
            shellHook =
              ''
                export CC=${old-stdenv.cc}/bin/cc
              ''
              + shellHook;
            packages = shellPackages;
          };

          default = crane-old-cc;
        };
      }
    );
}
