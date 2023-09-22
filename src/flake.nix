{
  description = "Flake utils demo";
  inputs.flake-utils.url = "github:numtide/flake-utils";
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
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
            version = self.packages.${system}.darshan-runtime.version;
            src = self.packages.${system}.darshan-runtime.src;
            buildInputs = self.packages.${system}.darshan-runtime.buildInputs;
            propagatedBuildInputs = [ pkgs.perl pkgs.gnuplot pkgs.python3 pkgs.bash ];
            configurePhase = ''
              ./prepare.sh
              cd darshan-util/
              ./configure --prefix=$out
            '';
          };
          neo4j-4 = builtins.fetchTarball {
            url = https://neo4j.com/artifact.php?name=neo4j-community-4.1.1-unix.tar.gz;
            sha256 = "sha256:0ja23145ff9f8di6a2q349hanyq7s93p55vbm00zqslr80xga2k9";
          };
          spade = pkgs.stdenv.mkDerivation {
            pname = "SPADE";
            version = "2.0.0";
            buildInputs = [ pkgs.jdk11 pkgs.pkg-config pkgs.uthash ];
            propagatedBuildInputs = [ pkgs.jdk11 ];
            patches = [ ./spade.diff ];
            configurePhase = ''
              mkdir lib/neo4j-community-4.1.1
              cp -r ${neo4j-4}/* lib/neo4j-community-4.1.1
              ./configure --prefix=$out
              patchShebangs --build bin/*
            '';
            src = pkgs.fetchFromGitHub {
              owner = "ashish-gehani";
              repo = "SPADE";
              rev = "master";
              hash = "sha256-5Cvx9Z1Jn30wEqP+X+/rPviZZKiEOjRGvd1KJfg5Www=";
            };
          };
          benchexec = pkgs.python311.pkgs.buildPythonPackage rec {
            pname = "BenchExec";
            version = "3.17";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "f35cbb98a7e3b7d66fb70c701ba28404a7594a0f4e9e65ea931f87195b08f28f";
            };
            propagatedBuildInputs = [ pkgs.python311.pkgs.pyyaml ];
            checkInputs = [ pkgs.python311.pkgs.nose pkgs.busybox ];
            doCheck = false;
            pythonImportsCheck = [ "benchexec" ];
          };
          charmonium-time-block = pkgs.python311.pkgs.buildPythonPackage rec {
            pname = "charmonium.time_block";
            version = "0.3.2";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "dbd15cf34e753117f25c404594ad984d91d658552a647ea680b1affd2b6374ce";
            };
            propagatedBuildInputs = [ pkgs.python311.pkgs.psutil ];
            checkInputs = [ pkgs.python311.pkgs.pytest ];
            pythonImportsCheck = [ "charmonium.time_block" ];
          };
          env = pkgs.symlinkJoin {
            name = "env";
            paths = [
              # Deps of prov:
              self.packages.${system}.darshan-runtime
              self.packages.${system}.darshan-util
              self.packages.${system}.spade
              pkgs.fsatrace
              pkgs.strace
              pkgs.ltrace

              # Deps of runner script and notebook workloads
              (pkgs.python311.withPackages (pypkgs: [
                # Deps of script
                pypkgs.mypy
                pypkgs.pandas
                pypkgs.matplotlib
                pypkgs.kaggle
                pypkgs.tqdm
                pypkgs.ipython
                self.packages.${system}.benchexec
                self.packages.${system}.charmonium-time-block

                # deps of notebooks
                pypkgs.numpy # repeats are OK
                pypkgs.pandas
                pypkgs.matplotlib
                pypkgs.notebook
                pypkgs.seaborn
                pypkgs.scipy
                pypkgs.scikit-learn
                pypkgs.nbconvert
                (pypkgs.jupyter-contrib-nbextensions.overrideAttrs (self: super: {
                  # Yes, this was very recently broken by [1]
                  # But it was even more recently fixed by [2].
                  # But it has not yet been marked as fixed.
                  # So I will do that manually here.
                  # [1]: https://github.com/ipython-contrib/jupyter_contrib_nbextensions/issues/1647
                  # [2]: https://github.com/NixOS/nixpkgs/commit/ba873b2be6252a5144c9f37fae1341973ac155ae
                  meta.broken = false;
                  patches = (({ patches = []; } // super).patches) ++ [
                    (pkgs.fetchpatch {
                      name = "notebook-v7-compat.patch";
                      url = "https://github.com/ipython-contrib/jupyter_contrib_nbextensions/commit/181e5f38f8c7e70a2e54a692f49564997f21a231.patch";
                      hash = "sha256-WrC9npEUAk3Hou8Tp8kK+Nw+H0bEEjR3GIoUTxrZxak=";
                    })
                  ];
                }))
              ]))

              # deps of notebooks
              # pkgs.util-linux
              # pkgs.iproute2

              # Deps of runner script
              pkgs.ruff
              pkgs.libseccomp.lib

              # Deps of Spack workloads
              # https://spack.readthedocs.io/en/latest/getting_started.html
              pkgs.stdenv.cc # https://ryantm.github.io/nixpkgs/stdenv/stdenv/#sec-tools-of-stdenv
              pkgs.gnumake
              pkgs.gnupatch
              pkgs.bash
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
              pkgs.gnused
              pkgs.gnugrep
              pkgs.gawk
              pkgs.libnsl
              pkgs.libxcrypt.out
            ];
          };
        };
      }
    )
  ;
}
