{
  inputs.flake-utils.url = "github:numtide/flake-utils";
  outputs = {
    self,
      nixpkgs,
      flake-utils,
      ...
  } @ inputs: let
    lib = nixpkgs.lib;
    systems = ["x86_64-linux"];
  in
    flake-utils.lib.eachSystem systems (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
      in rec {
        packages = rec {
          rpaths = python.pkgs.buildPythonPackage rec {
            pname = "rpaths";
            version = "1.0.0";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "dd7418b2c837e1b4eb5c5490465d5f282645143e4638c809ddd250dc33395641";
            };
            pythonImportsCheck = [pname];
          };
          distro = python.pkgs.buildPythonPackage rec {
            pname = "distro";
            version = "1.8.0";
            format = "pyproject";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "02e111d1dc6a50abb8eed6bf31c3e48ed8b0830d1ea2a1b78c61765c2513fdd8";
            };
            buildInputs = [python.pkgs.setuptools];
            pythonImportsCheck = [pname];
          };
          usagestats = python.pkgs.buildPythonPackage rec {
            pname = "usagestats";
            version = "1.0.1";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "d8887aa0f65769b1423b784e626ec6fb6ba6ed1432667e10d6115b783571be6d";
            };
            buildInputs = [python.pkgs.pip];
            propagatedBuildInputs = [distro python.pkgs.requests];
            pythonImportsCheck = [pname];
            # Check tries to upload usage statistics to localhost over TCP which will not work in the Nix sandbox
            doCheck = false;
          };
          reprozip = python.pkgs.buildPythonApplication rec {
            pname = "reprozip";
            version = "1.2";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "a98b7f04c52c60072e3c42da21997d3ad41161ff6cb1139e18cda8d3012120f9";
            };
            checkInputs = [python.pkgs.pip];
            buildInputs = [pkgs.sqlite];
            propagatedBuildInputs = [
              rpaths
              usagestats
              distro
              python.pkgs.pyyaml
              python.pkgs.setuptools
              pkgs.dpkg
            ];
            pythonImportsCheck = [pname];
          };
        };
      }
    );
}
