{
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
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
            buildInputs = [pkg];
            buildPhase =
              builtins.concatStringsSep
              "\n"
              (builtins.map
                (pairs: "install -D ${pkg}/${builtins.elemAt pairs 0} $out/${builtins.elemAt pairs 1}")
                file-pairs);
          };
      in {
        packages = {
          python-dbg = python312-debug;
        };
        devShells = {
          default = pkgs.mkShell {
            buildInputs =
              [
                (pkgs.python312.withPackages (pypkgs: [
                  pypkgs.psutil
                  pypkgs.typer
                  pypkgs.pycparser
                  pypkgs.pytest
                  pypkgs.mypy
                  pypkgs.pygraphviz
                  pypkgs.networkx
                  pypkgs.ipython
                  pypkgs.pydot
                  pypkgs.rich
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
                if builtins.elem system lib.platforms.linux
                then [pkgs.xdot]
                else []
              );
          };
        };
      }
    );
}
