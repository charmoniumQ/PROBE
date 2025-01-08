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
  outputs = {
    self,
    nixpkgs,
    flake-utils,
    nix-utils,
    nix-documents,
  }:
    flake-utils.lib.eachDefaultSystem
    (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      nix-lib = nixpkgs.lib;
      nix-utils-lib = nix-utils.lib.${system};
      nix-documents-lib = nix-documents.lib.${system};
      svg2pdf = dstName: srcName: pkgs.runCommand dstName {} "${pkgs.librsvg}/bin/rsvg-convert --output=$out --format=pdf ${srcName}";

    in {
      devShells = {
        default = pkgs.mkShell {
          packages = [
            (pkgs.texlive.combine { inherit (pkgs.texlive) scheme-full; })
            pkgs.pandoc
            pkgs.librsvg
            pkgs.haskellPackages.pandoc-crossref
          ];
        };
      };
      packages = {
        test = (pkgs.texlive.combine { inherit (pkgs.texlive) scheme-medium; });
        default = self.packages."${system}".acm-rep;
        acm-rep = nix-utils-lib.mergeDerivations {
          packageSet =
            nix-utils-lib.packageSetRec
            (self: [
              (pkgs.stdenvNoCC.mkDerivation rec {
                src = nix-utils-lib.mergeDerivations {
                  packageSet =
                    {
                      "." = ./benchmark_suite;
                      "zotero.bib" = ./zotero.bib;
                      "reed.bib" = ./reed.bib;
                      "supplemental.bib" = ./supplemental.bib;
                      "acm-template.tex" = ./acm-template.tex;
                      "citations-to-latex.lua" = ./citations-to-latex.lua;
                    }
                    // nix-utils-lib.packageSet [
                      self."app-lvl-prov.pdf"
                      self."wf-lvl-prov.pdf"
                      self."sys-lvl-prov.pdf"
                      self."sys-lvl-log.pdf"
                      self."prov-example.pdf"
                    ];
                };
                mainSrc = "README.md";
                latexStem = "main";
                latexTemplate = "acm-template.tex";
                name = "benchmark_suite";
                date = 1707292740;
                latexmkFlagForEngine = "-pdf";
                pandocFlagForEngine = "latexmk"; # pdfLaTeX vs LuaLaTeX vs XeLaTeX
                FONTCONFIG_FILE = pkgs.makeFontsConf {fontDirectories = [];};
                buildInputs = [
                  (pkgs.texlive.combine { inherit (pkgs.texlive) scheme-medium; })
                  pkgs.pandoc
                ];
                buildPhase = ''
                  tmp=$(mktemp --directory)
                  HOME=$(mktemp --directory)
                  export SOURCE_DATE_EPOCH=${builtins.toString date}
                  ${pkgs.pandoc}/bin/pandoc \
                       --output=${latexStem}-plain.tex \
                       --lua-filter=citations-to-latex.lua \
                       --pdf-engine=${pandocFlagForEngine} \
                       --template=${latexTemplate} \
                       --metadata-file=<(echo {"styles": {"removed": "removed", "added": "default", "only-in-new": "default", "only-in-old": "removed", "only-in-trans": "removed"}}) \
                       ${mainSrc}
                  ${pkgs.pandoc}/bin/pandoc \
                       --output=${latexStem}.tex \
                       --lua-filter=citations-to-latex.lua \
                       --pdf-engine=${pandocFlagForEngine} \
                       --template=${latexTemplate} \
                       --metadata-file=<(echo {"styles": {"removed": "red", "added": "green", "only-in-new": "default", "only-in-old": "removed", "only-in-trans": "default"}}) \
                       ${mainSrc}
                  # lacheck ${latexStem}.tex
                  set +e
                  latexmk ${latexmkFlagForEngine} -shell-escape -emulate-aux-dir -auxdir=$tmp -Werror ${latexStem}
                  ls -ahlt
                  latexmk ${latexmkFlagForEngine} -shell-escape -emulate-aux-dir -auxdir=$tmp -Werror ${latexStem}-plain
                  ls -ahlt
                  latexmk_status=$?
                  set -e
                  ${pkgs.pdftk}/bin/pdftk ${latexStem}.pdf ${latexStem}-plain.pdf cat output ${latexStem}-full.pdf
                  mkdir $out/
                  cp *.{svg,pdf,bbl,tex,docx} $out/
                  set -x
                  archive=acmrep24-11
                  mkdir $archive
                  mkdir $archive/pdf $archive/Source
                  cp main.pdf $archive/pdf/main.pdf
                  cp *.{pdf,svg,bbl,bib,tex} $archive/Source/
                  cp --recursive generated $archive/Source
                  # Remove specific files that TAPS doesn't like
                  rm $archive/Source/{main*.pdf,README.pdf,acm-template.tex,main.tex}
                  env --chdir $archive ${pkgs.zip}/bin/zip -r $out/$archive.zip ./
                  if [ $latexmk_status -ne 0 ]; then
                    cp $tmp/${latexStem}.log $out
                    echo "Aborting: Latexmk failed"
                    cat $tmp/${latexStem}.log
                    # exit $latexmk_status
                  fi
                '';
                phases = ["unpackPhase" "buildPhase"];
              })
              (nix-documents-lib.graphvizFigure {
                src = ./benchmark_suite;
                main = "app-lvl-prov.dot";
                name = "app-lvl-prov.pdf";
                outputFormat = "pdf";
                layoutEngine = "dot";
              })
              (nix-documents-lib.graphvizFigure {
                src = ./benchmark_suite;
                main = "wf-lvl-prov.dot";
                name = "wf-lvl-prov.pdf";
                outputFormat = "pdf";
                layoutEngine = "dot";
              })
              (nix-documents-lib.graphvizFigure {
                src = ./benchmark_suite;
                main = "sys-lvl-prov.dot";
                name = "sys-lvl-prov.pdf";
                outputFormat = "pdf";
                layoutEngine = "dot";
              })
              (nix-documents-lib.graphvizFigure {
                src = ./benchmark_suite;
                main = "prov-example.dot";
                name = "prov-example.pdf";
                outputFormat = "pdf";
                layoutEngine = "dot";
              })
              (svg2pdf "sys-lvl-log.pdf" ./benchmark_suite/sys-lvl-log.svg)
            ]);
        };
      };
    });
}
