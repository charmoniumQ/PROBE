{
  inputs.flake-utils.url = "github:numtide/flake-utils";
  # Use newer Nix to apply this bugfix
  # https://github.com/NixOS/nix/pull/10467
  inputs.new-nixos.url = "github:NixOS/nixpkgs";
  outputs = {
    self,
      nixpkgs,
      flake-utils,
      ...
  } @ inputs:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        noPytest = pypkg:
          pypkg.overrideAttrs (self: super: {
            pytestCheckPhase = ''true'';
          });
        removePackage = drv: pkgsToRemove:
          drv.override (builtins.listToAttrs (builtins.map (pkgToRemove: {
            name = pkgToRemove;
            value = null;
          })
            pkgsToRemove));
        renameInDrv = drv: oldFile: newFile:
          pkgs.runCommand "${drv.name}-renamed" {} ''
            mkdir $out
            cp --recursive ${drv}/* $out
            chmod +w $out/${oldFile} $(dirname $out/${newFile})
            mv $out/${oldFile} $out/${newFile}
          '';
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
        scandir = python.pkgs.buildPythonPackage rec {
          pname = "scandir";
          version = "1.10.0";
          src = pkgs.fetchPypi {
            inherit pname version;
            sha256 = "4d4631f6062e658e9007ab3149a9b914f3548cb38bfb021c64f39a025ce578ae";
          };
          pythonImportsCheck = [pname];
        };
      in rec {
        packages = rec {
          nix = inputs.new-nixos.legacyPackages.${system}.nix;
          strace = pkgs.strace;
          fsatrace = pkgs.fsatrace;
          rr = pkgs.rr;
          coreutils = pkgs.coreutils;
          glibc_bin = pkgs.glibc.bin;
          lzop = pkgs.lzop;
          lighttpd = pkgs.lighttpd;
          hey = pkgs.hey;
          nginx = pkgs.nginx;
          curl = pkgs.curl;
          gnused = pkgs.gnused;
          which = pkgs.which;
          procps = pkgs.procps;
          hello = pkgs.hello;
          gcc = pkgs.gcc;
          tex = pkgs.texlive.combined.scheme-full;
          gnumake = pkgs.gnumake.out;
          bash = pkgs.bash.out;
          http-python-env = pkgs.symlinkJoin {
            name = "http-python-env";
            paths = [
              pkgs.bash
              curl
              hey
              pkgs.psmisc
              (pkgs.python312.withPackages (pypkgs: [
                pypkgs.psutil
              ]))
            ];
          };
          un-archive-env = pkgs.symlinkJoin {
            name = "un-archve-env";
            paths = [
              pkgs.bash
              pkgs.coreutils
              (pkgs.gnutar.overrideAttrs (super: {
                patches =
                  (
                    if (super ? patches)
                    then super.patches
                    else []
                  )
                  ++ [./tar.patch];
              }))
              pkgs.gzip
              pkgs.pigz
              pkgs.bzip2
              pkgs.pbzip2
              pkgs.xz
              pkgs.lzop
            ];
          };
          kaggle = python.withPackages (pypkgs: [
            pypkgs.kaggle
          ]);
          tornado = python.pkgs.tornado;
          kaggle-notebook-env = (python.withPackages (pypkgs: [
            pypkgs.pandas
            pypkgs.tqdm
            pypkgs.matplotlib
            pypkgs.notebook
            pypkgs.seaborn
            pypkgs.scipy
            pypkgs.scikit-learn
            pypkgs.xgboost
            pypkgs.lightgbm
          ]));
          kaggle-notebook-titanic-0 = pkgs.stdenv.mkDerivation {
            name = "kaggle-notebook-titanic-0";
            src = ./kaggle/titanic-tutorial.ipynb;
            dontUnpack = true;
            buildPhase = ''
              cp $src tmp
              substituteInPlace tmp \
                --replace '/kaggle/input/titanic' '${kaggle-data-titanic}' \
                --replace "'/kaggle/input'" "'${kaggle-data-titanic}'" \
                --replace "'submission.csv'" "os.environ['OUTPUT'] + '/submission.csv'"
              cp tmp $out
            '';
          };
          kaggle-notebook-house-prices-0 = pkgs.stdenv.mkDerivation {
            name = "kaggle-notebook-house-prices-0";
            src = ./kaggle/comprehensive-data-exploration-with-python.ipynb;
            dontUnpack = true;
            buildPhase = ''
              cp $src tmp
              substituteInPlace tmp \
                --replace '../input' '${kaggle-data-house-prices}'
              cp tmp $out
            '';
          };
          kaggle-notebook-titanic-1 = pkgs.stdenv.mkDerivation {
            name = "kaggle-notebook-titanic-1";
            src = ./kaggle/titanic-data-science-solutions.ipynb;
            dontUnpack = true;
            buildPhase = ''
              cp $src tmp
              substituteInPlace tmp \
                --replace '../input' '${kaggle-data-titanic}' \
                --replace "'../output" "os.environ('OUTPUT') + '"
              cp tmp $out
            '';
          };
          kaggle-notebook-house-prices-1 = pkgs.stdenv.mkDerivation {
            name = "kaggle-notebook-house-prices-1";
            src = ./kaggle/stacked-regressions-top-4-on-leaderboard.ipynb;
            dontUnpack = true;
            buildPhase = ''
              cp $src tmp
              substituteInPlace tmp \
                --replace '../input' '${kaggle-data-house-prices}' \
                --replace '\"ls\"' '\"${coreutils}/bin/ls\"' \
                --replace "'submission.csv'" "os.environ['OUTPUT'] + '/submission.csv'" \
                --replace "import numpy as np" "import numpy as np, os"
              cp tmp $out
            '';
          };
          # These are not downloadable without logging in, so I will host them here
          kaggle-data-titanic = pkgs.stdenv.mkDerivation {
            name = "kaggle-data-titanic";
            src = ./kaggle/titanic.zip;
            buildInputs = [ pkgs.unzip ];
            unpackPhase = ''
              mkdir source
              unzip $src -d source
              cd source
            '';
            buildPhase = ''
              mkdir $out
              cp -r * $out/
            '';
          };
          kaggle-data-house-prices = pkgs.stdenv.mkDerivation {
            name = "kaggle-data-house-prices";
            src = ./kaggle/house-prices.zip;
            buildInputs = [ pkgs.unzip ];
            unpackPhase = ''
              mkdir source
              unzip $src -d source
              cd source
            '';
            buildPhase = ''
              mkdir $out
              cp -r * $out/
            '';
          };
          spack-env = pkgs.symlinkJoin {
            name = "spack-env";
            paths = [
              pkgs.stdenv.cc # https://ryantm.github.io/nixpkgs/stdenv/stdenv/#sec-tools-of-stdenv
              pkgs.gfortran
              pkgs.gfortran.cc
              pkgs.gnupatch
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
              pkgs.findutils
              pkgs.which
            ];
          };
          linux-env = pkgs.symlinkJoin {
            name = "linux-env";
            paths = [
              pkgs.bison
              pkgs.flex
              pkgs.bc
              pkgs.bash
              pkgs.diffutils
              pkgs.elfutils.dev
              pkgs.elfutils.out
              pkgs.openssl.dev
              pkgs.openssl.out
              pkgs.perl
              pkgs.gnumake
              pkgs.coreutils
              pkgs.gnused
              pkgs.stdenv.cc
              pkgs.findutils
              pkgs.gnugrep
              pkgs.gawk
            ];
          };
          # Rename to avoid conflict when merging
          apacheHttpd = renameInDrv pkgs.apacheHttpd "bin/httpd" "bin/apacheHttpd";
          miniHttpd = renameInDrv pkgs.miniHttpd "bin/httpd" "bin/miniHttpd";
          postmark-bin = pkgs.stdenv.mkDerivation rec {
            pname = "postmark";
            version = "1.53";
            src = pkgs.fetchzip {
              url = "http://deb.debian.org/debian/pool/main/p/postmark/postmark_${version}.orig.tar.gz";
              hash = "sha256-Dkk2TrNQGjpaliob06xQKji/qMnGLemUxAkLvJh4HzM=";
            };
            installPhase = ''
              ls -ahlt
              mkdir --parents $out/bin $out/share/man/man1
              cp postmark $out/bin
              cp postmark.1 $out/share/man/man1
            '';
          };

          # parrot = pkgs.stdenv.mkDerivation rec {
          #   pname = "parrot";
          #   version = "0.9.15";
          #   src = pkgs.fetchurl {
          #     url = "https://pages.cs.wisc.edu/~thain/research/parrot/parrot-0_9_15.tar.gz";
          #     hash = "sha256-8LF1glOqKzAUpzC7uQMCNgEDX1+9MCfs4PEm0EJWdEE=";
          #   };
          #   buildInputs = [ pkgs.gdbm ];
          #   dontAddPrefix = true;
          #   preConfigure = ''
          #     configureFlagsArray+=(--prefix $out --with-gdbm-path ${pkgs.gdbm.out});
          #   '';
          #   installPhase = ''
          #     install parrot $out/bin
          #   '';
          # };
          darshan-runtime = pkgs.stdenv.mkDerivation rec {
            pname = "darshan-runtime";
            version = "3.4.4";
            src = pkgs.fetchFromGitHub {
              owner = "darshan-hpc";
              repo = "darshan";
              rev = "darshan-${version}";
              hash = "sha256-hNuLGKxJjpVogqoXMtUSMIgZlOQyA3nCM1s7ia2Y8kM=";
            };
            buildInputs = [pkgs.zlib pkgs.autoconf pkgs.automake pkgs.libtool];
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
            propagatedBuildInputs = [pkgs.perl pkgs.gnuplot pkgs.python3 pkgs.bash];
            configurePhase = ''
              ./prepare.sh
              cd darshan-util/
              ./configure --prefix=$out
            '';
          };
          spade = (
            let
              mainSrc = pkgs.fetchFromGitHub {
                owner = "ashish-gehani";
                repo = "SPADE";
                rev = "master";
                hash = "sha256-5Cvx9Z1Jn30wEqP+X+/rPviZZKiEOjRGvd1KJfg5Www=";
                name = "main";
              };
              neo4j = pkgs.fetchurl {
                url = https://neo4j.com/artifact.php?name=neo4j-community-4.1.1-unix.tar.gz;
                hash = "sha256-T2Y6UgvsQN/QsZcv6zz5OvMhwjC0SK223JF3F+Z6EnE=";
              };
              jdk = pkgs.jdk11;
              jre = pkgs.jdk11;
              scriptDeps = [pkgs.ps jre];
            in
              pkgs.stdenv.mkDerivation {
                pname = "SPADE";
                version = "2.0.0";
                buildInputs = [jdk pkgs.uthash pkgs.fuse];
                nativeBuildInputs = [pkgs.makeWrapper pkgs.pkg-config];
                patches = [./spade.diff];
                srcs = [mainSrc neo4j];
                sourceRoot = mainSrc.name;
                postUnpack = "mv neo4j-community-4.1.1 ${mainSrc.name}/lib/";
                preBuild = "patchShebangs --build bin/*";
                postInstall = ''
                  wrapProgram $out/bin/spade --prefix PATH : ${pkgs.lib.makeBinPath scriptDeps}
                '';
                PKG_CONFIG_PATH = "${pkgs.fuse}/lib/pkgconfig";
              }
          );
          pcre2-dev = pkgs.pcre2.dev.overrideAttrs (super: {
            postFixup =
              super.postFixup
              + ''
                ${pkgs.gnused}/bin/sed --in-place s=/bin/sh=${pkgs.bash}/bin/bash=g $dev/bin/pcre2-config
              '';
          });
          pyTimecard = python.pkgs.buildPythonPackage rec {
            pname = "Timecard";
            version = "3.0.0";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "efa3a55b6efdd548158e2693bd788d59e8b7df68e7a88fbb3692eeb0d24c876f";
            };
          };
          ftpbench = python.pkgs.buildPythonApplication rec {
            pname = "ftpbench";
            version = "1.0";
            # Note the version on PyPI is not Python3 :(
            src = pkgs.fetchFromGitHub {
              owner = "selectel";
              repo = pname;
              rev = "42dd3bb6a4623b628668167bcceee3210a050ada";
              hash = "sha256-FIWwhGp6ucwFcMSeFJmnRSdCzcCEIRXViWMP4O4hjko=";
            };
            propagatedBuildInputs = [
              python.pkgs.setuptools
              python.pkgs.gevent
              python.pkgs.dnspython
              pyTimecard
              python.pkgs.docopt
            ];
          };
          proftpd = pkgs.stdenv.mkDerivation rec {
            pname = "proftpd";
            version = "1.3.8";
            srcs = [
              (pkgs.fetchFromGitHub {
                owner = "proftpd";
                repo = pname;
                rev = "v${version}";
                hash = "sha256-DnVUIcrE+mW4vTZzoPk+dk+2O3jEjGbGIBiVZgcvkNA=";
                name = "proftpd";
              })
              (pkgs.fetchFromGitHub {
                owner = "Castaglia";
                repo = "proftpd-mod_vroot";
                rev = "v0.9.11";
                hash = "sha256-wAf7zmCr2sMH/EKNxWtUjIEoaAFenzNyfXd4sKjvHDY=";
                name = "proftpd-mod_vroot";
              })
            ];
            sourceRoot = ".";
            postUnpack = ''
              chmod --recursive u+w proftpd-mod_vroot
              cp --recursive proftpd-mod_vroot proftpd/contrib/mod_vroot
              cd proftpd
            '';
            buildInputs = [pkgs.libxcrypt];
            configureFlags = ["--with-modules=mod_vroot"];
            installPhase = ''
              install --directory $out/bin
              install --target-directory $out/bin proftpd ftpcount ftpdctl ftpscrub ftpshut ftptop ftpwho contrib/ftpasswd contrib/ftpquota contrib/ftpmail
            '';
          };
          yafc = pkgs.stdenv.mkDerivation {
            pname = "yafc";
            version = "1.3.7";
            src = pkgs.fetchFromGitHub {
              owner = "sebastinas";
              repo = "yafc";
              rev = "v1.3.7";
              hash = "sha256-kg9pxlPl7nU3ayUEmmimrgHg1uVd2mMB2Fo8fW65TiQ=";
            };
            # buildInputs = [ pkgs.glib.dev pkgs.gnulib.out ];
            nativeBuildInputs = [pkgs.autoconf pkgs.automake pkgs.glib.dev pkgs.gnulib.out pkgs.pkg-config pkgs.m4 pkgs.libtool pkgs.texinfo];
            buildInputs = [pkgs.libssh];
            configurePhase = ''
              glib-gettextize -f -c

              # https://gitweb.gentoo.org/repo/gentoo.git/commit/?id=c13b5e88c6e9c7bd2698d844cb5ed127ed809f7e
              rm m4/glib-gettext.m4

              autoreconf -v -f -i

              ./configure
            '';
            installPhase = ''
              install --directory $out/bin
              install --target-directory $out/bin yafc
            '';
          };
          lftp = pkgs.lftp;
          wget = pkgs.wget;
          libseccomp = pkgs.libseccomp.lib;

          ###################
          # True benchmarks #
          ###################

          blast-benchmark-orig = pkgs.fetchzip {
            url = "https://ftp.ncbi.nlm.nih.gov/blast/demo/benchmark/benchmark2013.tar.gz";
            hash = "sha256-BbEGS79KXKjqr4OfI5FWD6Ki0CRmR3AFJKAIsc42log=";
          };
          blast-benchmark = pkgs.runCommand "blast-benchmark-modified" {} ''
            mkdir $out
            cp -r ${blast-benchmark-orig}/* $out
            rm $out/Makefile
            sed '
                 s/OUTPUT=/OUTPUT?=/;
                 s/TIME=.*//;
                 s/[12]>[^ ][^ ]*//g;
                 1i export PATH:=${pkgs.blast}/bin:${pkgs.blast-bin}/bin:${pkgs.bash}/bin:$(PATH)
            ' ${blast-benchmark-orig}/Makefile > $out/Makefile
          '';
          # Sed commands in order for blast-benchmark:
          # - Make OUTPUT overridable..
          # - Remove TIME
          # - Remove stdout and stderr redirection
          # - Add BLAST, blast-bin, and sh to path.
          #   Note that makembindex (required for idx_megablast is contained in pkgs.blast-bin but not pkgs.blast)

          postmark = pkgs.stdenv.mkDerivation rec {
            pname = "postmark";
            version = "1.5";
            src = pkgs.fetchurl {
              url = "https://web.archive.org/web/20070320010728if_/http://www.netapp.com:80/ftp/postmark-1_5.c";
              hash = "sha256-/vtxTGDOuvtJ/kkAIK4GMPV9x3ww/yDL887ukOae+2k=";
            };
            dontUnpack = true;
            buildPhase = ''
              cc $src -Wall -Wextra -O3 -o postmark
            '';
            installPhase = ''
              install --directory $out/bin
              install postmark $out/bin
            '';
          };
          lmbench = pkgs.stdenv.mkDerivation {
            pname = "lmbench";
            version = "3.0.a9";
            # src = pkgs.fetchzip {
            #   url = "https://sourceforge.net/projects/lmbench/files/development/lmbench-3.0-a9/lmbench-3.0-a9.tgz";
            #   hash = "sha256-vGS9f/oy9KjYqcdG0XOUUbPJCLw7hG4WpbNFcORzL6I=";
            #   name = "lmbench";
            # };
            # sourceRoot = "lmbench";
            # For some reason, this is not reliably downloadable; therefore, I will vendor a copy
            src = ./lmbench-3.0-a9;
            sourceRoot = "lmbench-3.0-a9";
            buildInputs = [pkgs.libtirpc.dev pkgs.coreutils pkgs.findutils];
            patchPhase = ''
              sed -i 's=/bin/rm=rm=g' src/Makefile Makefile
              sed -i 's/CFLAGS=-O/CFLAGS="$(CFLAGS) -O"/g' src/Makefile
              sed -i 's=printf(buf)=printf("%s", buf)=g' src/lat_http.c
              sed -i 's=../bin/$OS/='"$out/bin/=g" scripts/config-run
              sed -i 's=../scripts/=$out/bin/=g' scripts/config-run
              sed -i 's|C=.*|C=lmbench-config|g' scripts/config-run
            '';
            # A shell array containing additional arguments passed to make. You must use this instead of makeFlags if the arguments contain spaces
            preBuild = ''
              mkdir $out
              makeFlagsArray+=(
                CFLAGS="-O3 -I${pkgs.libtirpc.dev}/include/tirpc"
                LDFLAGS="-L${pkgs.libtirpc.dev}/lib -ltirpc"
                --trace
                               )
            '';
            installPhase = ''
              ls -ahlt bin/
              ./scripts/os
              ./scripts/gnu-os
              mkdir --parents $out/bin
              cp bin/x86_64-linux-gnu/* $out/bin
              cp scripts/{config-run,version,config} $out/bin
            '';
          };
          lmbench-debug = lmbench.overrideAttrs (super: {
            preBuild = ''
              mkdir $out
              makeFlagsArray+=(
                CFLAGS="-Og -I${pkgs.libtirpc.dev}/include/tirpc -D_DEBUG=1"
                LDFLAGS="-L${pkgs.libtirpc.dev}/lib -ltirpc"
                --trace
              )
            '';
          });
          splash3 = pkgs.stdenv.mkDerivation rec {
            pname = "splash";
            version = "3";
            src = pkgs.fetchFromGitHub {
              owner = "SakalisC";
              repo = "Splash-3";
              rev = "master";
              hash = "sha256-HFgqYEHanlwA0FA/7kOSsmcPzcb8BLJ3lG74DV5RtBA=";
            };
            a = "hi";
            patches = [./splash-3.diff];
            nativeBuildInputs = [pkgs.m4 pkgs.binutils];
            sourceRoot = "source/codes";
            buildPhase = ''
              ${pkgs.gnused}/bin/sed --in-place s=inputs/car.geo=$out/inputs/raytrace/car.geo=g apps/raytrace/inputs/car.env
              ${pkgs.gnused}/bin/sed --in-place s=inputs/car.rl=car.rl=g apps/raytrace/inputs/car.env
              ${pkgs.gnused}/bin/sed --in-place s=random.in=$out/inputs/water-nsquared/random.in=g apps/water-nsquared/initia.c.in
              ${pkgs.gnused}/bin/sed --in-place s=random.in=$out/inputs/water-spatial/random.in=g apps/water-spatial/initia.c.in
              make all
            '';
            installPhase = ''
              mkdir $out $out/bin $out/inputs
              for app in barnes fmm radiosity raytrace volrend water-nsquared water-spatial; do
                APP=$(echo "$app" | tr 'a-z' 'A-Z')
                cp apps/$app/$APP $out/bin
                if [ -d apps/$app/inputs ]; then
                  mkdir $out/inputs/$app
                  cp apps/$app/inputs/* $out/inputs/$app
                fi
              done
              cp apps/water-nsquared/random.in $out/inputs/water-nsquared/
              cp apps/water-spatial/random.in $out/inputs/water-spatial/
              cp apps/ocean/contiguous_partitions/OCEAN $out/bin
              for app in cholesky fft radix; do
                APP=$(echo "$app" | tr 'a-z' 'A-Z')
                cp kernels/$app/$APP $out/bin
                if [ -d kernels/$app/inputs ]; then
                  mkdir $out/inputs/$app
                  cp kernels/$app/inputs/* $out/inputs/$app
                fi
              done
              cp kernels/lu/contiguous_blocks/LU $out/bin
            '';
          };
          git = pkgs.git;
          mercurial = pkgs.mercurial;
          gcc_multi_bin = pkgs.gcc_multi.bin;
          ltrace-conf = pkgs.runCommand "ltrace-conf" {} ''
            cp ${./ltrace.conf} $out
          '';
          ltrace = pkgs.ltrace.overrideAttrs (super: {
            patches = super.patches ++ [./ltrace.patch];
          });
          cde = pkgs.cde.overrideAttrs (super: {
            patches = [./cde.patch];
          });
          care = pkgs.stdenv.mkDerivation rec {
            pname = "care";
            version = "5.4.0";
            src = pkgs.fetchFromGitHub {
              repo = "proot";
              owner = "proot-me";
              rev = "v${version}";
              sha256 = "sha256-Z9Y7ccWp5KEVuo9xfHcgo58XqYVdFo7ck1jH7cnT2KA=";
            };
            postPatch = ''
              substituteInPlace src/GNUmakefile \
                --replace /bin/echo ${pkgs.coreutils}/bin/echo
              # our cross machinery defines $CC and co just right
              sed -i /CROSS_COMPILE/d src/GNUmakefile
            '';
            buildInputs = [pkgs.ncurses pkgs.talloc pkgs.uthash pkgs.libarchive];
            nativeBuildInputs = [pkgs.pkg-config pkgs.docutils pkgs.makeWrapper];
            makeFlags = ["-C src" "care"];
            postBuild = ''
              make -C doc care/man.1
            '';
            installFlags = ["PREFIX=${placeholder "out"}"];
            installTargets = "install-care";
            postInstall = ''
              install -Dm644 doc/care/man.1 $out/share/man/man1/care.1
              wrapProgram $out/bin/care --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.lzop ]}
            '';
            # proot provides tests with `make -C test` however they do not run in the sandbox
            doCheck = false;
          };
          nextflow = pkgs.nextflow;
          snakemake = pkgs.snakemake;
          transformers-python = pkgs.python312.withPackages (pypkgs: [ pypkgs.setuptools ]);
          transformers-src = pkgs.fetchFromGitHub {
            owner = "huggingface";
            repo = "transformers";
            rev = "v4.48.0";
            hash = "sha256-jh2bMmvTC0G0kLJl7xXpsvXvBmlbZEDA88AfosoE9sA=";
          };
          pkg-config = pkgs.pkg-config.out;
          tesseract-env = pkgs.symlinkJoin {
            name = "tesseract-env";
            paths = [
              pkgs.bash
              pkgs.coreutils
              pkgs.gnugrep
              pkgs.gnum4
              pkgs.gnused
              pkgs.diffutils
              pkgs.gawk
              pkgs.leptonica
              pkgs.which
              pkgs.icu.dev
              pkgs.pango.dev
              pkgs.cairo.dev
              # https://tesseract-ocr.github.io/tessdoc/Compiling.html
              pkgs.gcc
              pkgs.autoconf
              pkgs.automake
              pkgs.libtool
              pkgs.pkg-config
              pkgs.libpng
              pkgs.libjpeg
              pkgs.libtiff
              pkgs.zlib.dev
              pkgs.libwebp
              pkgs.giflib
              pkgs.libarchive
              pkgs.curl.dev
            ];
          };
          tesseract-src = pkgs.fetchFromGitHub {
            owner = "tesseract-ocr";
            repo = "tesseract";
            rev = "5.5.0";
            hash = "sha256-qyckAQZs3gR1NBqWgE+COSKXhv3kPF+iHVQrt6OPi8s=";
          };
          rsync = pkgs.rsync;
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
            ];
            pythonImportsCheck = [pname];
          };
          reprounzip-docker = python.pkgs.buildPythonPackage rec {
            pname = "reprounzip-docker";
            version = "1.2";
            src = pkgs.fetchPypi {
              inherit pname version;
              sha256 = "ccde16c7502072693afd7ab9d8b58f478e575efe3806ec4951659869a571fa2f";
            };
            checkInputs = [python.pkgs.pip];
            doCheck = false;
            propagatedBuildInputs = [rpaths reprounzip];
            pythonImportsCheck = ["reprounzip.unpackers.docker"];
          };
          provenance-to-use = pkgs.stdenv.mkDerivation rec {
            pname = "provenance-to-use";
            version = "0.0.0";
            src = pkgs.fetchFromGitHub {
              owner = "depaul-dice";
              repo = pname;
              rev = "chex";
              hash = "sha256-IwYwEWSxTAp62JkNZUAaDeoF5kyizofMCCQvlrtGzBM=";
            };
            cmakeFlags = [
              "-DBUILD_TESTING=OFF"
              "-DCMAKE_BUILD_TYPE=Release"
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
          mandala = python.pkgs.buildPythonPackage rec {
            pname = "mandala";
            version = "3.20";
            src = pkgs.fetchFromGitHub {
              owner = "amakelov";
              repo = "mandala";
              rev = "v0.2.0-alpha";
              hash = "sha256-MunDxlF23kn8ZJM7rk++bZaN35L51w2CABL16MZXDXU=";
            };
            propagatedBuildInputs = [
              python.pkgs.numpy
              python.pkgs.pandas
              python.pkgs.joblib
              python.pkgs.tqdm
              python.pkgs.pyarrow
              python.pkgs.prettytable
              python.pkgs.graphviz
            ];
            checkInputs = [
              python.pkgs.pytest
              python.pkgs.hypothesis
              python.pkgs.ipython
            ];
            # Check tries to manipulate cgroups and /sys which will not work inside the Nix sandbox
            doCheck = true;
            pythonImportsCheck = [ "mandala" ];
          };
        };
        devShells = {
          default = pkgs.mkShell {
            packages = [
              (python.withPackages (pypkgs: [
                pypkgs.typer
                pypkgs.rich
                pypkgs.mypy
                pypkgs.pyyaml
                pypkgs.ipython
                pypkgs.yarl
                pypkgs.tqdm
                pypkgs.types-tqdm
                pypkgs.types-pyyaml
                pypkgs.polars
                pypkgs.types-psutil
                pypkgs.requests
                pypkgs.githubkit
                pypkgs.aiohttp
                pypkgs.aiodns
                pypkgs.tqdm
                packages.mandala
              ]))
            ];
          };
        };
      }
    );
}
