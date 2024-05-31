{
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = nixpkgs.legacyPackages.${system}; in
      {
        devShells = {
          default = pkgs.mkShell {
            buildInputs = [
              (pkgs.python312.withPackages (pypkgs: [
                pypkgs.pycparser
                pypkgs.pytest
                pypkgs.mypy
                pypkgs.ipython
              ]))
              pkgs.tree
              pkgs.strace
              pkgs.ltrace
              pkgs.gcc
              pkgs.gdb
              pkgs.coreutils
              pkgs.bash
              pkgs.valgrind
            ];
          };
        };
      }
    );
}
