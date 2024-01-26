{
  inputs = {
    flake-utils = {
      url = "github:numtide/flake-utils";
    };
    nix-utils = {
      url = "github:charmoniumQ/nix-utils";
    };
    nix-documents = {
      url = "github:charmoniumQ/nix-documents";
    };
  };
  outputs = { self, nixpkgs, flake-utils, nix-utils, nix-documents }:
    flake-utils.lib.eachDefaultSystem
      (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          nix-lib = nixpkgs.lib;
          nix-utils-lib = nix-utils.lib.${system};
          nix-documents-lib = nix-documents.lib.${system};
        in
        {
          packages = {
            default = nix-utils-lib.mergeDerivations {
              packageSet = nix-utils-lib.packageSetRec
                (self: [
                  (nix-documents-lib.markdownDocument {
                    src = nix-utils-lib.mergeDerivations {
                      packageSet = {
                        "." = ./benchmark_suite;
                        "zotero.bib" = ./zotero.bib;
                      }
                      // nix-utils-lib.packageSet [
                        self."app-lvl-prov.svg"
                        self."wf-lvl-prov.svg"
                        self."sys-lvl-prov.svg"
                      ]
                      ;
                    };
                    main = "README.md";
                    name = "benchmark_suite.pdf";
                    pdfEngine = "xelatex";
                    outputFormat = "pdf";
                    date = 1655528400;
                    nixPackages = [ ];
                  })
                  (nix-documents-lib.graphvizFigure {
                    src = ./benchmark_suite;
                    main = "app-lvl-prov.dot";
                    name = "app-lvl-prov.svg";
                    outputFormat = "svg";
                    layoutEngine = "dot";
                  })
                  (nix-documents-lib.graphvizFigure {
                    src = ./benchmark_suite;
                    main = "wf-lvl-prov.dot";
                    name = "wf-lvl-prov.svg";
                    outputFormat = "svg";
                    layoutEngine = "dot";
                  })
                  (nix-documents-lib.graphvizFigure {
                    src = ./benchmark_suite;
                    main = "sys-lvl-prov.dot";
                    name = "sys-lvl-prov.svg";
                    outputFormat = "svg";
                    layoutEngine = "dot";
                  })
                ]);
            };
          };
        });
}
