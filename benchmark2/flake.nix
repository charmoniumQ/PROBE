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
            buildInputs = [python.pkgs.setuptools];
            pythonImportsCheck = [pname];
            pyproject = true;
          };
          distro = python.pkgs.buildPythonPackage rec {
            pname = "distro";
            version = "1.8.0";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "02e111d1dc6a50abb8eed6bf31c3e48ed8b0830d1ea2a1b78c61765c2513fdd8";
            };
            buildInputs = [python.pkgs.setuptools];
            pythonImportsCheck = [pname];
            pyproject = true;
          };
          usagestats = python.pkgs.buildPythonPackage rec {
            pname = "usagestats";
            version = "1.0.1";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "d8887aa0f65769b1423b784e626ec6fb6ba6ed1432667e10d6115b783571be6d";
            };
            buildInputs = [python.pkgs.pip python.pkgs.setuptools];
            propagatedBuildInputs = [distro python.pkgs.requests];
            pythonImportsCheck = [pname];
            # Check tries to upload usage statistics to localhost over TCP which will not work in the Nix sandbox
            doCheck = false;
            pyproject = true;
          };
          sciunit-dedup = pkgs.stdenv.mkDerivation rec {
            pname = "sciunit-dedup";
            version = "0.0.0";
            src = pkgs.fetchFromGitHub {
              owner = "depaul-dice";
              repo = pname;
              # https://github.com/depaul-dice/sciunit/blob/4c8011ddbf4f8ca7da6b987572d6de56d70661dc/CMakeLists.txt#L27
              rev = "7400941338892fef17791dd6dc3465cd280d99b2";
              hash = "sha256-eRtaYjIJHZi/ZEXj7Jd1g7kzDvafxWQzV45okoQmRik=";
            };
            nativeBuildInputs = [pkgs.cmake];
            patches = [
              ./sciunit-dedup.patch
              # https://github.com/depaul-dice/sciunit/blob/4c8011ddbf4f8ca7da6b987572d6de56d70661dc/CMakeLists.txt
            ];
            installPhase = ''
            install -d $out/bin
            install -t $out/bin demo/vv demo/dump_blocks
          '';
          };
          scripter = pkgs.stdenv.mkDerivation rec {
            pname = "scripter";
            version = "0.0.0";
            src = pkgs.fetchFromGitHub {
              owner = "depaul-dice";
              repo = pname;
              rev = "master";
              hash = "sha256-Z80106btm0MKf2IUuolJK5kJG0FCWBi3zBu0AN9eNRI=";
            };
            nativeBuildInputs = [pkgs.cmake];
            installPhase = ''
            install -d $out/bin
            install -t $out/bin scripter
          '';
          };
          utcdatetime = python.pkgs.buildPythonPackage rec {
            pname = "utcdatetime";
            version = "0.0.7";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "806d96da79fd129efade31e8e917a19ea602b047e5b6c3db12c0d69828a779f4";
            };
            pythonImportsCheck = [pname];
            nativeCheckInputs = [
              (python.pkgs.strict-rfc3339.overrideAttrs (_: {doCheck = false;}))
              python.pkgs.freezegun
              python.pkgs.pytz
            ];
            patches = [
              (pkgs.fetchurl {
                url = "https://patch-diff.githubusercontent.com/raw/fawkesley/python-utcdatetime/pull/32.patch";
                sha256 = "07m5plgdd1r9lggb3mia2mjbw8sz4hkp01hq48r0xfkl3zc5pvfh";
              })
            ];
          };
          provenance-to-use = pkgs.stdenv.mkDerivation rec {
            pname = "provenance-to-use";
            version = "0.0.0";
            src = pkgs.fetchFromGitHub {
              owner = "depaul-dice";
              repo = pname;
              rev = "master";
              hash = "sha256-PLOI3aYway8oWCvftHzTE92AQBqpH1nBlGp2dtSjDuY=";
            };
            cmakeFlags = [
              "-DBUILD_TESTING=OFF"
              "-DCMAKE_BUILD_TYPE=Release"
              "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"
            ];
            patches = [./provenance-to-use.patch];
            nativeBuildInputs = [pkgs.cmake pkgs.makeWrapper];
            buildInputs = [pkgs.coreutils];
            installPhase = ''
              install -d $out/bin
              install -t $out/bin ptu
              wrapProgram $out/bin/ptu --prefix PATH : ${pkgs.lib.strings.makeBinPath [pkgs.coreutils]}
            '';
          };
          provenance-to-use-dir = pkgs.writeShellScriptBin "ptu" ''
            destination="$1"
            shift
            ${provenance-to-use}/bin/ptu "$@"
            ${pkgs.coreutils}/bin/rm --recursive --force "$destination"
            ${pkgs.coreutils}/bin/mv cde-package "$destination"
          '';
          scandir = python.pkgs.buildPythonPackage rec {
            pname = "scandir";
            version = "1.10.0";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "4d4631f6062e658e9007ab3149a9b914f3548cb38bfb021c64f39a025ce578ae";
            };
            pythonImportsCheck = [pname];
          };
          hs_restclient = python.pkgs.buildPythonPackage rec {
            pname = "hs_restclient";
            version = "1.3.7";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "313c5905220bfb659db0fc188b00e65b2094e92b9a7fc91ed7824aa9aae3b2cd";
            };
            propagatedBuildInputs = [
              python.pkgs.requests
              python.pkgs.requests_toolbelt
              python.pkgs.oauthlib
              python.pkgs.requests_oauthlib
            ];
            pythonImportsCheck = [pname];
          };
          sciunit2 = python.pkgs.buildPythonApplication rec {
            pname = "sciunit2";
            version = "0.4.post82.dev130189670";
            patches = [./sciunit2.patch];
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "a1ab36634ab7a1abe46f478b90643eb128ace56f85bda007dfe95525392fc876";
            };
            postUnpack = ''
              # sciunit2 source tarball from PyPI contains non-portable binaries
              # We will delete these, which forces sciunit2 to find the Nix-build binaries
              # Also see sciunit2.patch
              rm sciunit2-*/sciunit2/libexec/{ptu,scripter,vv}
            '';
            postFixup = ''
              wrapProgram $out/bin/sciunit --prefix PATH : ${(pkgs.lib.strings.makeBinPath [pkgs.gnutar])}
            '';
            pythonImportsCheck = [pname];
            propagatedBuildInputs = [
              # https://github.com/depaul-dice/sciunit/blob/4c8011ddbf4f8ca7da6b987572d6de56d70661dc/CMakeLists.txt
              provenance-to-use
              sciunit-dedup
              scripter
              utcdatetime
              scandir
              hs_restclient
              python.pkgs.tzlocal
              python.pkgs.zipfile2
              python.pkgs.retry
              python.pkgs.humanfriendly
              python.pkgs.configobj
              python.pkgs.contextlib2
              python.pkgs.setuptools
              python.pkgs.tqdm
              pkgs.gnutar
            ];
            nativeBuildInputs = [python.pkgs.pip pkgs.makeWrapper];
            nativeCheckInputs = [
              python.pkgs.pytest
              python.pkgs.mock
              python.pkgs.requests-mock
              python.pkgs.freezegun
              python.pkgs.ddt
              python.pkgs.testpath
              python.pkgs.numpy
              provenance-to-use
              sciunit-dedup
              scripter
            ];
            dontCheck = true;
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
            pyproject = true;
          };
          reprounzip = python.pkgs.buildPythonPackage rec {
            pname = "reprounzip";
            version = "1.3";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "3f0b6b4dcde9dbcde9d283dfdf154c223b3972d5aff41a1b049224468bba3496";
            };
            checkInputs = [python.pkgs.pip];
            propagatedBuildInputs = [
              rpaths
              usagestats
              distro
              python.pkgs.requests
              python.pkgs.pyyaml
              python.pkgs.pyelftools
              python.pkgs.setuptools
            ];
            pythonImportsCheck = [pname];
            pyproject = true;
          };
        };
      }
    );
}
