{
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python312-debug = pkgs.python312.overrideAttrs (self: super: {
          configureFlags = super.configureFlags ++ ["--with-pydebug"];
        });
      in
      {
        devShells = {
          default = pkgs.mkShell {
            buildInputs = [
              (python312-debug.withPackages (pypkgs: [
                pypkgs.typer
                pypkgs.pycparser
                pypkgs.pytest
                pypkgs.mypy
                pypkgs.ipython
              ]))
              pkgs.gcc
              pkgs.gdb
              pkgs.coreutils
              pkgs.bash
              pkgs.mrsh
              pkgs.yash
              pkgs.dash
              pkgs.gash
              pkgs.mksh
            ];
          };
        };
      }
    );
}
