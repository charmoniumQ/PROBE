{
  description = "Flake utils demo";

  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;
      in
      rec {
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
            pythonImportsCheck = [ "charmonium.freeze" ];
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
            pythonImportsCheck = [ "charmonium.cache" ];
          };
          shirty = python.pkgs.buildPythonPackage {
            pname = "shirty";
            version = "0.10.1";
            src = pkgs.fetchzip {
              url = "https://cee-gitlab.sandia.gov/atlas-team/shirty/-/archive/0.10.1/shirty-0.10.1.tar.gz";
              hash = "sha256-Bd5QE+LWHFSEyNzHlCiRx58qiPJdYlN0HqG683fbRFs=";
            };
            format = "setuptools";
            pythonImportsCheck = [ "shirty" ];
          };
        };
        devShells = {
          default = pkgs.mkShell {
            packages = [
              (python.withPackages (pypkgs: [
                pypkgs.httpx
                pypkgs.polars
                pypkgs.matplotlib
                pypkgs.seaborn
                pypkgs.yarl
                pypkgs.githubkit
                pypkgs.tqdm

                # Dev tools
                pypkgs.ipython
                pypkgs.typing-extensions
                packages.charmonium-cache
              ]))
              pkgs.ty
            ];
            shellHook = "source ./shell_vars.sh";
          };
        };
      }
    );
}
