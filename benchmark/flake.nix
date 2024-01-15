{
  inputs.flake-utils.url = "github:numtide/flake-utils";
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python310;
        noPytest = pypkg: pypkg.overrideAttrs (self: super: {
          pytestCheckPhase = ''true'';
        });
      in
      {
        packages = rec {
          darshan-runtime = pkgs.stdenv.mkDerivation rec {
            pname = "darshan-runtime";
            version = "3.4.4";
            src = pkgs.fetchFromGitHub {
              owner = "darshan-hpc";
              repo = "darshan";
              rev = "darshan-${version}";
              hash = "sha256-hNuLGKxJjpVogqoXMtUSMIgZlOQyA3nCM1s7ia2Y8kM=";
            };
            buildInputs = [ pkgs.zlib pkgs.autoconf pkgs.automake pkgs.libtool ];
            configurePhase = ''
              ./prepare.sh
              cd darshan-runtime/
              ./configure \
                --with-mem-align=${mem-align} \
                --with-jobid-env=${jobid-env} \
                --with-username-env=${username-env} \
                --with-log-path-by-env=${log-path-by-env} \
                --without-mpi \
                --prefix=$out
            '';
            # Darshan variables:
            jobid-env = "NONE";
            mem-align = "8";
            username-env = "USER";
            log-path-by-env = "DARSHAN_LOG_PATH";
          };
          darshan-util = pkgs.stdenv.mkDerivation rec {
            pname = "darshan-util";
            version = darshan-runtime.version;
            src = darshan-runtime.src;
            buildInputs = darshan-runtime.buildInputs;
            propagatedBuildInputs = [ pkgs.perl pkgs.gnuplot pkgs.python3 pkgs.bash ];
            configurePhase = ''
              ./prepare.sh
              cd darshan-util/
              ./configure --prefix=$out
            '';
          };
          spade = (
            let
              mainSrc = (pkgs.fetchFromGitHub {
                owner = "ashish-gehani";
                repo = "SPADE";
                rev = "master";
                hash = "sha256-5Cvx9Z1Jn30wEqP+X+/rPviZZKiEOjRGvd1KJfg5Www=";
                name = "main";
              });
              neo4j = pkgs.fetchurl {
                url = https://neo4j.com/artifact.php?name=neo4j-community-4.1.1-unix.tar.gz;
                hash = "sha256-T2Y6UgvsQN/QsZcv6zz5OvMhwjC0SK223JF3F+Z6EnE=";
              };
              jdk = pkgs.jdk11;
              jre = pkgs.jdk11;
              scriptDeps = [ pkgs.ps jre ];
            in pkgs.stdenv.mkDerivation {
              pname = "SPADE";
              version = "2.0.0";
              buildInputs = [ jdk pkgs.uthash pkgs.fuse ];
              nativeBuildInputs = [ pkgs.makeWrapper pkgs.pkg-config ];
              patches = [ ./spade.diff ];
              srcs = [ mainSrc neo4j ];
              sourceRoot = mainSrc.name;
              postUnpack = "mv neo4j-community-4.1.1 ${mainSrc.name}/lib/";
              preBuild = "patchShebangs --build bin/*";
              postInstall = ''
                wrapProgram $out/bin/spade --prefix PATH : ${pkgs.lib.makeBinPath scriptDeps}
              '';
              PKG_CONFIG_PATH = "${pkgs.fuse}/lib/pkgconfig";
            }
          );
          benchexec = python.pkgs.buildPythonPackage rec {
            pname = "BenchExec";
            version = "3.20";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "e796e8636772825aa7c72aa3aaf0793522e3d0d55eb9220f7706421d4d3f38a9";
            };
            propagatedBuildInputs = [ python.pkgs.pyyaml python.pkgs.pystemd ];
            checkInputs = [ python.pkgs.nose pkgs.busybox python.pkgs.lxml ];
            # Check tries to manipulate cgroups and /sys which will not work inside the Nix sandbox
            doCheck = false;
            pythonImportsCheck = [ "benchexec" ];
          };
          charmonium-time-block = python.pkgs.buildPythonPackage rec {
            pname = "charmonium.time_block";
            version = "0.3.2";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "dbd15cf34e753117f25c404594ad984d91d658552a647ea680b1affd2b6374ce";
            };
            propagatedBuildInputs = [ python.pkgs.psutil ];
            checkInputs = [ python.pkgs.pytest ];
            pythonImportsCheck = [ "charmonium.time_block" ];
            nativeCheckInputs = [ python.pkgs.pytestCheckHook ];
          };
          rpaths = python.pkgs.buildPythonPackage rec {
            pname = "rpaths";
            version = "1.0.0";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "dd7418b2c837e1b4eb5c5490465d5f282645143e4638c809ddd250dc33395641";
            };
            pythonImportsCheck = [ pname ];
          };
          distro = python.pkgs.buildPythonPackage rec {
            pname = "distro";
            version = "1.8.0";
            format = "pyproject";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "02e111d1dc6a50abb8eed6bf31c3e48ed8b0830d1ea2a1b78c61765c2513fdd8";
            };
            buildInputs = [ python.pkgs.setuptools ];
            pythonImportsCheck = [ pname ];
          };
          usagestats = python.pkgs.buildPythonPackage rec {
            pname = "usagestats";
            version = "1.0.1";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "d8887aa0f65769b1423b784e626ec6fb6ba6ed1432667e10d6115b783571be6d";
            };
            buildInputs = [ python.pkgs.pip ];
            propagatedBuildInputs = [ distro python.pkgs.requests ];
            pythonImportsCheck = [ pname ];
            # Check tries to upload usage statistics to localhost over TCP which will not work in the Nix sandbox
            doCheck = false;
          };
          reprozip = python.pkgs.buildPythonPackage rec {
            pname = "reprozip";
            version = "1.2";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "a98b7f04c52c60072e3c42da21997d3ad41161ff6cb1139e18cda8d3012120f9";
            };
            checkInputs = [ python.pkgs.pip ];
            buildInputs = [ pkgs.sqlite ];
            propagatedBuildInputs = [ rpaths usagestats distro python.pkgs.pyyaml pkgs.dpkg ];
            pythonImportsCheck = [ pname ];
          };
          reprounzip = python.pkgs.buildPythonPackage rec {
            pname = "reprounzip";
            version = "1.3";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "3f0b6b4dcde9dbcde9d283dfdf154c223b3972d5aff41a1b049224468bba3496";
            };
            checkInputs = [ python.pkgs.pip ];
            propagatedBuildInputs = [ python.pkgs.pyyaml rpaths usagestats python.pkgs.requests distro python.pkgs.pyelftools ];
            pythonImportsCheck = [ pname ];
          };
          reprounzip-docker = python.pkgs.buildPythonPackage rec {
            pname = "reprounzip-docker";
            version = "1.2";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "ccde16c7502072693afd7ab9d8b58f478e575efe3806ec4951659869a571fa2f";
            };
            checkInputs = [ python.pkgs.pip ];
            doCheck = false;
            propagatedBuildInputs = [ rpaths reprounzip ];
            pythonImportsCheck = [ "reprounzip.unpackers.docker" ];
          };
          provenance-to-use = pkgs.stdenv.mkDerivation rec {
            pname = "provenance-to-use";
            version = "0.0.0";
            src = pkgs.fetchFromGitHub {
              owner = "depaul-dice";
              repo = pname;
              rev = "chex";
              hash = "sha256-NsTljrFzEl43BCT1Oq6KL6UEBKIW4qI3jXZ814FGgEY=";
            };
            patches = [ ./provenance-to-use.patch ];
            nativeBuildInputs = [ pkgs.cmake ];
            installPhase = ''
              install -d $out/bin
              install -t $out/bin ptu
            '';
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
            nativeBuildInputs = [ pkgs.cmake ];
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
            nativeBuildInputs = [ pkgs.cmake ];
            installPhase = ''
              install -d $out/bin
              install -t $out/bin scripter
            '';
          };
          scandir = python.pkgs.buildPythonPackage rec {
            pname = "scandir";
            version = "1.10.0";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "4d4631f6062e658e9007ab3149a9b914f3548cb38bfb021c64f39a025ce578ae";
            };
            pythonImportsCheck = [ pname ];
          };
          utcdatetime = python.pkgs.buildPythonPackage rec {
            pname = "utcdatetime";
            version = "0.0.7";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "806d96da79fd129efade31e8e917a19ea602b047e5b6c3db12c0d69828a779f4";
            };
            pythonImportsCheck = [ pname ];
            nativeCheckInputs = [
              python.pkgs.nose
              python.pkgs.strict-rfc3339
              python.pkgs.freezegun
              python.pkgs.pytz
            ];
            patches = [ ./utcdatetime.patch ];
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
            pythonImportsCheck = [ pname ];
          };
          sciunit2 = python.pkgs.buildPythonPackage rec {
            pname = "sciunit2";
            version = "0.4.post82.dev130189670";
            patches = [ ./sciunit2.patch ];
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "a1ab36634ab7a1abe46f478b90643eb128ace56f85bda007dfe95525392fc876";
            };
            pythonImportsCheck = [ pname ];
            propagatedBuildInputs = [
              # https://github.com/depaul-dice/sciunit/blob/4c8011ddbf4f8ca7da6b987572d6de56d70661dc/CMakeLists.txt
              provenance-to-use
              sciunit-dedup
              scripter
              python.pkgs.tzlocal
              utcdatetime
              python.pkgs.zipfile2
              scandir
              python.pkgs.retry
              python.pkgs.humanfriendly
              python.pkgs.configobj
              python.pkgs.contextlib2
              python.pkgs.tqdm
              hs_restclient
            ];
            nativeBuildInputs = [ python.pkgs.pip ];
            nativeCheckInputs = [
              python.pkgs.nose
              python.pkgs.mock
              python.pkgs.requests-mock
              python.pkgs.freezegun
              python.pkgs.ddt
              python.pkgs.testpath
              python.pkgs.numpy
            ];
          };
          jupyter-contrib-nbextensions = python.pkgs.jupyter-contrib-nbextensions.overrideAttrs (self: super: {
            # Yes, this was very recently broken by [1]
            # But it was even more recently fixed by [2].
            # But it has not yet been marked as fixed.
            # So I will do that manually here.
            # [1]: https://github.com/ipython-contrib/jupyter_contrib_nbextensions/issues/1647
            # [2]: https://github.com/NixOS/nixpkgs/commit/ba873b2be6252a5144c9f37fae1341973ac155ae
            meta = { broken = false; };
            patches = (({ patches = []; } // super).patches) ++ [
              (pkgs.fetchpatch {
                name = "notebook-v7-compat.patch";
                url = "https://github.com/ipython-contrib/jupyter_contrib_nbextensions/commit/181e5f38f8c7e70a2e54a692f49564997f21a231.patch";
                hash = "sha256-WrC9npEUAk3Hou8Tp8kK+Nw+H0bEEjR3GIoUTxrZxak=";
              })
            ];
          });
          # arviz = noPytest (python.pkgs.arviz.override { numpyro = python.pkgs.tqdm; });
          # pymc3 = noPytest (python.pkgs.pymc3.override {
          #   arviz = arviz;
          #   pytensor = noPytest pytensor;
          # });
          # pytensor = noPytest (python.pkgs.pytensor.overrideAttrs (super: {
          #   src = pkgs.fetchFromGitHub {
          #     hash = "sha256-hWDUN6JRyQtxmAfWbP8YgzAAuLguf0k0kYdtHqLgEHI=";
          #     owner = "pymc-devs";
          #     repo = "pytensor";
          #     rev = "refs/tags/rel-2.18.1";
          #   };
          # }));
          fsatrace = pkgs.fsatrace.overrideAttrs (oldAttrs: {
            src = pkgs.fetchFromGitHub {
              owner = "jacereda";
              repo = "fsatrace";
              rev = "c031f8dae8f5456173157b3696f1c10f3c3c5b4a";
              hash = "sha256-rkDNuKkR1069eJI2XyIa0sKZMG4G1AiD4Zl+TVerw7w=";
            };
          });
          pcre2-dev = pkgs.pcre2.dev.overrideAttrs (super: {
            postFixup = super.postFixup + ''
              ${pkgs.gnused}/bin/sed --in-place s=/bin/sh=${pkgs.dash}/bin/dash=g $dev/bin/pcre2-config
            '';
          });
          env = pkgs.symlinkJoin {
            name = "env";
            paths = [
              # Provenance tools:
              darshan-runtime
              darshan-util
              spade
              fsatrace
              pkgs.strace
              pkgs.ltrace
              pkgs.cde
              pkgs.rr
              pkgs.dpkg
              pkgs.xdot

              # deps of notebooks
              pkgs.util-linux
              pkgs.iproute2
              pkgs.graphviz

              # Deps of pylsp
              pkgs.ruff

              # Deps of runner script
              pkgs.libseccomp.lib
              pkgs.glibc_multi.bin
              pkgs.glibc_multi
              pkgs.libfaketime
              pkgs.util-linux # for setarch

              # Benchmark
              pkgs.blast

              # Reproducibility tester
              pkgs.icdiff
              pkgs.disorderfs
              pkgs.fuse

              # Deps of build Apache
              pkgs.curl
              pkgs.apr.dev
              pkgs.aprutil.dev
              pcre2-dev

              # Deps of Spack workloads
              # https://spack.readthedocs.io/en/latest/getting_started.html
              pkgs.stdenv.cc # https://ryantm.github.io/nixpkgs/stdenv/stdenv/#sec-tools-of-stdenv
              pkgs.gfortran
              pkgs.gfortran.cc
              pkgs.gnupatch
              pkgs.gnutar
              pkgs.gzip
              pkgs.unzip
              pkgs.bzip2
              pkgs.xz
              pkgs.file
              pkgs.lsb-release
              pkgs.gnupg24
              pkgs.gitMinimal
              pkgs.coreutils
              # TODO: Add these to the package which uses them
              pkgs.gnumake
              pkgs.bash
              pkgs.gnused
              pkgs.gnugrep
              pkgs.gawk
              pkgs.libnsl
              pkgs.libxcrypt.out

              # Python pkgs!
              (python.withPackages (pypkgs: [
                # Provenance tools:
                reprozip
                reprounzip-docker
                sciunit2

                # Language server
                pypkgs.python-lsp-server
                pypkgs.mypy
                pypkgs.jedi
                pypkgs.pylsp-mypy
                pypkgs.python-lsp-black
                pypkgs.python-lsp-ruff

                # Deps of script
                pypkgs.pandas
                pypkgs.matplotlib
                pypkgs.kaggle
                pypkgs.tqdm
                pypkgs.ipython
                pypkgs.pyyaml
                pypkgs.types-pyyaml
                # arviz
                # pymc3
                pypkgs.graphviz
                benchexec
                charmonium-time-block

                # deps of notebooks
                pypkgs.numpy # repeats are OK
                pypkgs.pandas
                pypkgs.matplotlib
                pypkgs.notebook
                pypkgs.seaborn
                pypkgs.scipy
                pypkgs.scikit-learn
                pypkgs.nbconvert
                jupyter-contrib-nbextensions
              ]))
            ];
          };
        };
      }
    )
  ;
}

/*

(progn
 (remhash 'pyls lsp-clients)
 (remhash 'pylsp lsp-clients)
 (remhash 'mspyls lsp-clients)
 (lsp-register-client
  (make-lsp-client :new-connection (lsp-stdio-connection '("env" "-" "./result/bin/pylsp"))
                   :activation-fn (lsp-activate-on "python")
                   :server-id 'result-bin-pylsp))
)
*/
