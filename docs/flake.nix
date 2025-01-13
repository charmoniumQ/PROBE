{
  inputs = {
    flake-utils = {
      url = "github:numtide/flake-utils";
    };
  };
  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem
    (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      devShells = {
        default = pkgs.mkShell {
          packages = [
            (pkgs.texlive.combine { inherit (pkgs.texlive) scheme-full; })
            pkgs.pandoc
            pkgs.librsvg
            pkgs.inkscape
            pkgs.graphviz
            pkgs.python312
            pkgs.haskellPackages.pandoc-crossref
            pkgs.gnumake
          ];
        };
      };
    });
}
