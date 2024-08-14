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
    crane,
    flake-utils,
<<<<<<< HEAD
=======
    advisory-db,
>>>>>>> fa9144f (Fix glue code)
    rust-overlay,
    ...
  }@inputs: let
    supported-systems = [
      "x86_64-linux"
      "i686-linux"
      "aarch64-linux"
      "armv7l-linux"
    ];
  in
    flake-utils.lib.eachSystem supported-systems (system: let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [(import rust-overlay)];
      };
<<<<<<< HEAD
      python = pkgs.python312;
      frontend = (import ./probe_src/probe_frontend/frontend.nix) ({ inherit system pkgs python; } // inputs);
    in {
        packages = rec {
          probe-bundled = let
            # libprobe is a "private" package
            # It is only used in probe-bundled
            # TODO: The only public package should probably be probe-bundled and probe-py.
            libprobe = pkgs.stdenv.mkDerivation rec {
              pname = "libprobe";
              version = "0.1.0";
              src = ./probe_src/libprobe;
              makeFlags = [ "INSTALL_PREFIX=$(out)" "SOURCE_VERSION=${version}" ];
              buildInputs = [
=======
      inherit (pkgs) lib;
      python312-debug = pkgs.python312.overrideAttrs (oldAttrs: {
        configureFlags = oldAttrs.configureFlags ++ ["--with-pydebug"];
        # patches = oldAttrs.patches ++ [ ./python.patch ];
      });
      export-and-rename = pkg: file-pairs:
        pkgs.stdenv.mkDerivation {
          pname = "${pkg.pname}-only-bin";
          dontUnpack = true;
          version = pkg.version;
          buildInputs = [ pkg ];
          buildPhase =
            builtins.concatStringsSep
              "\n"
              (builtins.map
                (pairs: "install -D ${pkg}/${builtins.elemAt pairs 0} $out/${builtins.elemAt pairs 1}")
                file-pairs);
        };
      rust-stuff = (import ./probe_src/probe_frontend/rust-stuff.nix) ({ inherit system pkgs; } // inputs);
      in {
        packages = rec {
          python-dbg = python312-debug;
          libprobe-interface = pkgs.stdenv.mkDerivation {
            pname = "libprobe-interface";
            version = "0.1.0";
            src = ./probe_src/libprobe-interface;
            dontBuild = true;
            installPhase = ''
              install -D --target-directory $out/include/ *.h
            '';
          };
          arena = pkgs.stdenv.mkDerivation {
            pname = "arena";
            version = "0.1.0";
            src = ./probe_src/arena;
            dontBuild = true;
            installPhase = ''
              install -D --target-directory $out/include/ *.h
            '';
          };
          libprobe = pkgs.stdenv.mkDerivation rec {
            pname = "libprobe";
            version = "0.1.0";
            src = ./probe_src/libprobe;
            makeFlags = [ "INSTALL_PREFIX=$(out)" "SOURCE_VERSION=${version}" ];
            buildInputs = [
              libprobe-interface
              arena
              (pkgs.python312.withPackages (pypkgs: [
                pypkgs.pycparser
              ]))
            ];
          };
          bundled-probe = pkgs.stdenv.mkDerivation rec {
            pname = "bundled-probe";
            version = "0.1.0";
            dontUnpack = true;
            dontBuild = true;
            installPhase = ''
              mkdir $out $out/lib $out/bin
              # TODO: Should this cp be ln or ln --symbolic?
              cp ${libprobe}/lib/* $out/lib
              cp ${self.packages.${system}.probe-cli}/bin/* $out/bin
            '';
          };
          probe-py-generated = pkgs.python312.pkgs.buildPythonPackage rec {
            pname = "probe_py.generated";
            version = "0.1.0";
            format = "flit";
            build-system = [
              pkgs.python312Packages.flit-core
            ];
            unpackPhase = ''
              cp --recursive ${self.packages.${system}.probe-frontend}/* .
              mkdir dist
            '';
          };
        } // rust-stuff.packages;
        checks = rust-stuff.checks;
        devShells = {
          default = pkgs.mkShell {
            buildInputs =
              [
>>>>>>> fa9144f (Fix glue code)
                (pkgs.python312.withPackages (pypkgs: [
                  pypkgs.pycparser
                ]))
              ];
            };
          in pkgs.stdenv.mkDerivation rec {
            pname = "probe-bundled";
            version = "0.1.0";
            dontUnpack = true;
            dontBuild = true;
            nativeBuildInputs = [ pkgs.makeWrapper ];
            installPhase = ''
              mkdir $out $out/bin
              makeWrapper \
                ${self.packages.${system}.probe-cli}/bin/probe \
                $out/bin/probe \
                --set __PROBE_LIB ${libprobe}/lib
            '';
          };
          probe-py-manual = python.pkgs.buildPythonPackage rec {
            pname = "probe_py.manual";
            version = "0.1.0";
            pyproject = true;
            build-system = [
              python.pkgs.flit-core
            ];
            src = ./probe_src/python;
            propagatedBuildInputs = [
              self.packages.${system}.probe-py-generated
              python.pkgs.networkx
              python.pkgs.pygraphviz
              python.pkgs.pydot
              python.pkgs.rich
              python.pkgs.typer
            ];
            pythonImportsCheck = [ pname ];
          };
          default = probe-bundled;
        } // frontend.packages;
        # TODO: Run pytest tests in Nix checks
        checks = self.packages.${system} // frontend.checks;
        devShells = {
          default = frontend.devShells.default.overrideAttrs (oldAttrs: rec {
            shellHook = ''
              pushd $(git rev-parse --show-toplevel)
              source ./setup_devshell.sh
              popd
            '';
            buildInputs =
              oldAttrs.buildInputs ++ [
                (python.withPackages (pypkgs: [
                  # probe_py.manual runtime requirements
                  pypkgs.networkx
                  pypkgs.pygraphviz
                  pypkgs.pydot
                  pypkgs.rich
                  pypkgs.typer

                  # probe_py.manual "dev time" requirements
                  pypkgs.psutil
                  pypkgs.pytest
                  pypkgs.mypy
                  pypkgs.ipython

                  # libprobe build time requirement
                  pypkgs.pycparser
                ]))
                # (export-and-rename python312-debug [["bin/python" "bin/python-dbg"]])
                pkgs.which
                pkgs.gnumake
                pkgs.gcc
                pkgs.coreutils
                pkgs.bash
                pkgs.alejandra
                pkgs.hyperfine
                pkgs.just
                pkgs.black
                pkgs.ruff
              ]
              ++ (
                # gdb broken on apple silicon
                if system != "aarch64-darwin"
                then [pkgs.gdb]
                else []
              )
              ++ (
                # while xdot isn't marked as linux only, it has a dependency (xvfb-run) that is
                if builtins.elem system pkgs.lib.platforms.linux
                then [pkgs.xdot]
                else []
              );
          });
        };
       }
    );
}
