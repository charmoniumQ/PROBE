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
    benchmark2 = {
      url = ./benchmark2;
      inputs = {
        nixpkgs.follows = "nixpkgs";
        flake-utils.follows = "flake-utils";
      };
    };
    charmonium-time-block = {
      url = "github:charmoniumQ/charmonium.time_block";
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
    benchmark2,
    charmonium-time-block,
    ...
  }: let
    targets = import ./targets.nix;
    probe-ver = "0.0.13";
  in
    flake-utils.lib.eachSystem
    (builtins.attrNames targets)
    (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        pythonOverridden = python.override {
          packageOverrides = final: prev: {
            "langchain-protocol" = prev.buildPythonPackage rec {
              pname = "langchain-protocol";
              version = "0.0.18";
              pyproject = true;
              src = pkgs.fetchPypi {
                pname = "langchain_protocol";
                inherit version;
                sha256 = "ec3e11782f1ed0c9db38e5a9ed01b0e7a0d3fba406faa8aef6594b73c56a63e6";
              };
              build-system = [prev.hatchling];
              dependencies = [prev.typing-extensions];
              doCheck = false;
            };
            "langchain-core" = prev.langchain-core.overridePythonAttrs (old: rec {
              version = "1.4.9";
              src = pkgs.fetchPypi {
                pname = "langchain_core";
                inherit version;
                sha256 = "f8078901145bed0466755277500a5a22822a7b628808c4c0a28d4fc88895fcf2";
              };
              sourceRoot = "langchain_core-${version}";
              dependencies = old.dependencies ++ [final."langchain-protocol"];
              doCheck = false;
            });
            "langgraph-checkpoint" = prev.langgraph-checkpoint.overridePythonAttrs (old: rec {
              version = "4.1.1";
              src = pkgs.fetchPypi {
                pname = "langgraph_checkpoint";
                inherit version;
                sha256 = "6c2bdb530c91f91d7d9c1bd100925d0fc4f498d418c17f3587d1526279482a25";
              };
              sourceRoot = "langgraph_checkpoint-${version}";
              dependencies = [final."langchain-core" prev.ormsgpack];
              doCheck = false;
            });
            "langgraph-prebuilt" = prev.langgraph-prebuilt.overridePythonAttrs (old: rec {
              version = "1.1.0";
              src = pkgs.fetchPypi {
                pname = "langgraph_prebuilt";
                inherit version;
                sha256 = "3c579cf6eed2d17f9c157c2d0fcaddcd8688524e7022d3b22b37a3bf4589d528";
              };
              sourceRoot = "langgraph_prebuilt-${version}";
              dependencies = [final."langchain-core" final."langgraph-checkpoint"];
              doCheck = false;
            });
            "langgraph-sdk" = prev.langgraph-sdk.overridePythonAttrs (old: rec {
              version = "0.4.2";
              src = pkgs.fetchPypi {
                pname = "langgraph_sdk";
                inherit version;
                sha256 = "b88f0f5f6328ac0680d6790614a905b2bcfa257f2276dba4e38f0e86db0aa738";
              };
              sourceRoot = "langgraph_sdk-${version}";
              dependencies = old.dependencies ++ [final."langchain-core" final."langchain-protocol" prev.websockets];
              pythonRelaxDeps = ["websockets"];
              doCheck = false;
            });
            "langgraph" = prev.langgraph.overridePythonAttrs (old: rec {
              version = "1.2.9";
              src = pkgs.fetchPypi {
                pname = "langgraph";
                inherit version;
                sha256 = "385f87bc1802c35af7e0aa479278ecba8582d103515eb48256cb2ddcd42d0bd4";
              };
              sourceRoot = "langgraph-${version}";
              dependencies = [
                final."langchain-core"
                final."langgraph-checkpoint"
                final."langgraph-prebuilt"
                final."langgraph-sdk"
                prev.pydantic
                prev.xxhash
              ];
              doCheck = false;
            });
            "langchain" = prev.langchain.overridePythonAttrs (old: rec {
              version = "1.3.13";
              src = pkgs.fetchPypi {
                pname = "langchain";
                inherit version;
                sha256 = "bcf874680f31e9970f0db2264509df5bc2115d9680e9d651d537eb49bf1a7d8a";
              };
              sourceRoot = "langchain-${version}";
              dependencies = [final."langchain-core" final."langgraph" prev.pydantic];
              doCheck = false;
            });
            "langchain-openai" = prev.langchain-openai.overridePythonAttrs (old: {
              dependencies = [final."langchain-core" prev.openai prev.tiktoken];
              doCheck = false;
            });
            "langchain-deepseek" = prev.langchain-deepseek.overridePythonAttrs (old: {
              dependencies = [final."langchain-core" final."langchain-openai"];
              doCheck = false;
            });
            "langchain_mcp_adapters" = prev.buildPythonPackage rec {
              pname = "langchain_mcp_adapters";
              version = "0.3.0";
              pyproject = true;
              src = pkgs.fetchPypi {
                inherit pname version;
                sha256 = "fa6c9497015eb2807de5d0c341a36e1d2445cecbae1f4a24e922fc5b94f1a36c";
              };
              build-system = [prev.pdm-backend];
              propagatedBuildInputs = [
                final."langchain-core"
                prev.mcp
                prev.typing-extensions
              ];
              pythonImportsCheck = ["langchain_mcp_adapters"];
              doCheck = false;
            };
          };
        };
        cli-wrapper-pkgs = cli-wrapper.packages."${system}";
        benchmark2-pkgs = benchmark2.packages."${system}";
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
        charmonium-time-block-pkg = charmonium-time-block.packages."${system}".py312;
      in rec {
        packages = rec {
          types-networkx = python.pkgs.buildPythonPackage rec {
            pname = "types-networkx";
            version = "3.5.0.20251001";
            src = pkgs.fetchPypi {
              pname = "types_networkx";
              inherit version;
              sha256 = "8e3c5c491ba5870d75e175751d70ddeac81df43caf2a64bae161e181f5e8ea7a";
            };
            pyproject = true;
            nativeBuildInputs = [python.pkgs.setuptools];
            propagatedBuildInputs = [python.pkgs.numpy];
          };
          datamodel-code-generator = python.pkgs.datamodel-code-generator.overridePythonAttrs (super: rec {
            version = "0.55.0";
            src = pkgs.fetchFromGitHub {
              owner = "koxudaxi";
              repo = "datamodel-code-generator";
              tag = version;
              hash = "sha256-zsLJv7gKhmnEIS/AUvnBzm+07QFQoMdiFo/PkfRyHek=";
            };
            disabledTests = [
              "perf"
            ];
            nativeCheckInputs =
              super.nativeCheckInputs
              ++ [
                python.pkgs.time-machine
                python.pkgs.inline-snapshot
                python.pkgs.watchfiles
              ];
          });
          inherit (benchmark2-pkgs) reprozip reprounzip provenance-to-use provenance-to-use-dir strace mcp-server-filesystem;
          inherit (cli-wrapper-pkgs) cargoArtifacts probe-cli probe-headers;
          libprobe = old-stdenv.mkDerivation rec {
            pname = "libprobe";
            version = probe-ver;
            VERSION = probe-ver;
            src = ./libprobe;
            postUnpack = ''
              mkdir $sourceRoot/generated
              cp ${probe-headers}/*.h $sourceRoot/generated/
            '';
            nativeBuildInputs = [
              pkgs.git
              (python.withPackages (pypkgs: [
                pypkgs.pycparser
                pypkgs.pyelftools
              ]))
            ];
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
              pkgs.clang
              pkgs.clang-analyzer
              pkgs.clang-tools
              pkgs.compiledb
              pkgs.cppcheck
              pkgs.cppclean
              pkgs.include-what-you-use
            ];
            checkPhase = ''
              # When a user builds this WITHOUT build sandbox isolation, the libc files appear to come from somewhere different.
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
          probe-py-headers = pkgs.runCommand "probe-py-headers" {} ''
            mkdir $out
            export PATH="${packages.datamodel-code-generator}/bin:${python}/bin/:$PATH"
            env \
              JSONSCHEMA_OUTFILE=${probe-headers}/headers.json \
              PYTHON_HEADER_OUTFILE=$out/headers.py \
              python ${./probe_py/generate_headers.py}
          '';
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
                cp ${probe-py-headers}/headers.py $out/probe_py/
              '';
            };
            propagatedBuildInputs = [
              charmonium-time-block-pkg
              python.pkgs.dulwich
              python.pkgs.frozendict
              python.pkgs.msgspec
              python.pkgs.networkx
              python.pkgs.numpy
              python.pkgs.pydot
              python.pkgs.pygraphviz
              python.pkgs.rich
              python.pkgs.sqlalchemy
              python.pkgs.tqdm
              python.pkgs.typer
              python.pkgs.xdg-base-dirs
            ];
            nativeCheckInputs = [
              packages.types-networkx
              pkgs.ruff
              python.pkgs.mypy
              python.pkgs.pytest
              python.pkgs.pytest-asyncio
              python.pkgs.pytest-timeout
              python.pkgs.types-tqdm
            ];
            checkPhase = ''
              runHook preCheck
              #ruff format --check probe_src # TODO: uncomment
              ruff check probe_py/
              python -c 'import probe_py'
              mypy --strict --package probe_py
              runHook postCheck
            '';
          };
          container-image = pkgs.dockerTools.buildImage {
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
            probe-workspace-audit
            probe-workspace-clippy
            probe-workspace-deny
            probe-workspace-doc
            probe-workspace-fmt
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
                    packages.probe-py
                    pytest
                    pytest-asyncio
                    pytest-timeout
                  ]))
                pkgs.buildah
                pkgs.clang
                pkgs.coreutils # so we can `probe record head ...`, etc.
                pkgs.docker
                pkgs.gnumake
                pkgs.nix
                pkgs.podman
              ]
              ++ pkgs.lib.lists.optional (system != "i686-linux" && system != "armv7l-linux") pkgs.jdk_headless;
            buildPhase = ''
              make --directory=examples/
              RUST_BAKCTRACE=1 pytest
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
          probe-python = pythonOverridden.withPackages (pypkgs: [
            # probe_py runtime requirements
            charmonium-time-block-pkg
            pypkgs.dulwich
            pypkgs.frozendict
            pypkgs.msgspec
            pypkgs.networkx
            pypkgs.numpy
            pypkgs.pydot
            pypkgs.rich
            pypkgs.sqlalchemy
            pypkgs.tqdm
            pypkgs.typer
            pypkgs.xdg-base-dirs
            pypkgs.polars
            pypkgs.pandas # Polars: writing with 'sqlalchemy' engine currently requires pandas.
            pypkgs.pyarrow
            pypkgs.statsmodels

            # probe_py "dev time" requirements
            packages.types-networkx
            packages.datamodel-code-generator
            pypkgs.ipython
            pypkgs.ipdb
            pypkgs.mypy
            pypkgs.pytest
            pypkgs.pytest-asyncio
            pypkgs.pytest-timeout
            pypkgs.types-tqdm
            pypkgs.langchain
            pypkgs.langchain-deepseek
            pypkgs.langchain_mcp_adapters

            # libprobe build time requirement
            pypkgs.pycparser
            pypkgs.pyelftools
          ]);
          shellHook = ''
            export PROBE_BUILDAH="${pkgs.buildah}/bin/buildah"
            export PROBE_PYTHON="${probe-python}/bin/python"
            pushd $(git rev-parse --show-toplevel) > /dev/null
            source ./setup_devshell.sh
            popd > /dev/null
          '';
          shellPackages =
            [
              pkgs.jq

              # Rust tools
              pkgs.cargo-audit
              pkgs.cargo-deny
              pkgs.cargo-hakari
              pkgs.cargo-machete

              # Replay tools
              pkgs.buildah
              pkgs.podman
              pkgs.file

              # Python env
              probe-python

              # C tools
              pkgs.clang-analyzer
              pkgs.clang-tools # must go after clang-analyzer
              pkgs.cppcheck
              pkgs.git
              pkgs.gnumake
              pkgs.include-what-you-use
              old-pkgs.criterion # unit testing framework

              # Programs for testing
              pkgs.coreutils
              pkgs.nix

              # For other lints
              pkgs.alejandra
              pkgs.just
              pkgs.ruff
              pkgs.codespell
            ]
            # OpenJDK doesn't build on some platforms
            ++ pkgs.lib.lists.optional (system != "i686-linux" && system != "armv7l-linux") pkgs.nextflow
            ++ pkgs.lib.lists.optional (system != "i686-linux" && system != "armv7l-linux") pkgs.jdk_headless
            # gdb broken on apple silicon
            ++ pkgs.lib.lists.optional (system != "aarch64-darwin") pkgs.gdb;
        in rec {
          # Instead, we use the new stdenv while explicitly setting $CC.
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
