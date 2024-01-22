{
  description = "Flake utils demo";
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.flake-utils.inputs.nixpkgs.follows = "nixpkgs";
  inputs.nix-documents.url = "github:charmoniumQ/nix-documents";
  inputs.nix-documents.inputs.nixpkgs.follows = "nixpkgs";
  inputs.nix-utils.url = "github:charmoniumQ/nix-utils";
  inputs.nix-documents.inputs.nix-utils.follows = "nix-utils";
  outputs = { self, nixpkgs, flake-utils, nix-documents, nix-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        packages = rec {
          application-level = nix-documents.lib.${system}.graphvizFigure {
            src = nix-utils.lib.${system}.mergeDerivations {
              packageSet = {
                "index.dot" = ./application-level.dot;
              };
            };
            outputFormat = "pdf";
          };
          workflow-level = nix-documents.lib.${system}.graphvizFigure {
            src = nix-utils.lib.${system}.mergeDerivations {
              packageSet = {
                "index.dot" = ./workflow-level.dot;
              };
            };
            outputFormat = "pdf";
          };
          system-level = nix-documents.lib.${system}.graphvizFigure {
            src = nix-utils.lib.${system}.mergeDerivations {
              packageSet = {
                "index.dot" = ./system-level.dot;
              };
            };
            outputFormat = "pdf";
          };
          main = nix-documents.lib.${system}.latexDocument {
            src = nix-utils.lib.${system}.mergeDerivations {
              packageSet = {
                "application-level.pdf" = application-level;
                "workflow-level.pdf" = workflow-level;
                "system-level.pdf" = system-level;
                "meat.tex" = ./meat.tex;
                "index.tex" = ./index.tex;
                "zotero.bib" = ./zotero.bib;
                "appendix.tex" = ./appendix.tex;
              };
            };
            texlivePackages = {
              inherit (pkgs.texlive)
                geometry
                hyperref
                cleveref
                booktabs
                graphics
                caption
              ;
            };
          };
          all-figs = nix-utils.lib.${system}.mergeDerivations {
            packageSet = {
              "application-level.pdf" = application-level;
              "workflow-level.pdf" = workflow-level;
              "system-level.pdf" = system-level;
              "index.pdf" = main;
              "meat.tex" = ./meat.tex;
              "index.tex" = ./index.tex;
              "zotero.bib" = ./zotero.bib;
              "appendix.tex" = ./appendix.tex;
            };
          };
        };
      }
    );
}
