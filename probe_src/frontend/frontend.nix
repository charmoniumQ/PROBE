{
  pkgs,
  craneLib,
  rust-target,
  advisory-db,
  system,
  python,
  lib,
}: rec {
  src = lib.cleanSource ./.;
  filter = name: type:
    !(builtins.any (x: x) [
      (lib.hasSuffix ".nix" name)
      (lib.hasPrefix "." (builtins.baseNameOf name))
    ]);

  # Common arguments can be set here to avoid repeating them later
  commonArgs = {
    inherit src;
    strictDeps = true;

    # all the crates in this workspace either use rust-bindgen or depend
    # on local crate that does.
    nativeBuildInputs = [
      pkgs.rustPlatform.bindgenHook
    ];

    # pygen needs to know where to write the python file
    preConfigurePhases = [
      "pygenConfigPhase"
    ];
    pygenConfigPhase = ''
      export PYGEN_OUTFILE="$(realpath ./python/probe_py/generated/ops.py)"
    '';

    CARGO_BUILD_TARGET = rust-target;
    CARGO_BUILD_RUSTFLAGS = "-C target-feature=+crt-static";
    CPATH = ../libprobe/include;
  };

  individualCrateArgs =
    commonArgs
    // {
      # inherit cargoArtifacts;
      inherit (craneLib.crateNameFromCargoToml {inherit src;}) version;
      # disable tests since we'll run them all via cargo-nextest
      doCheck = false;
    };

  packages = rec {
    # Build *just* the cargo dependencies (of the entire workspace),
    # so we can reuse all of that work (e.g. via cachix) when running in CI
    # It is *highly* recommended to use something like cargo-hakari to avoid
    # cache misses when building individual top-level-crates
    cargoArtifacts = craneLib.buildDepsOnly commonArgs;

    # Build the top-level crates of the workspace as individual derivations.
    # This allows consumers to only depend on (and build) only what they need.
    # Though it is possible to build the entire workspace as a single derivation,
    # so this is left up to you on how to organize things
    probe-frontend = craneLib.buildPackage (individualCrateArgs
      // {
        pname = "probe-frontend";
        cargoExtraArgs = "-p probe_frontend";
        installPhase = ''
          cp -r ./python/ $out
          cp ./LICENSE $out/LICENSE
        '';
      });
    probe-py-generated = let
      workspace = (builtins.fromTOML (builtins.readFile ./Cargo.toml)).workspace;
      # TODO: Simplify this
      # Perhaps by folding the substituteAllFiles into probe-py-generated (upstream) or probe-py-frontend (downstream)
      # Could we combine all the packages?
    in
      python.pkgs.buildPythonPackage rec {
        src = pkgs.substituteAllFiles rec {
          src = probe-frontend;
          files = [
            "./pyproject.toml"
            "./LICENSE"
            "./probe_py/generated/__init__.py"
            "./probe_py/generated/ops.py"
            "./probe_py/generated/parser.py"
          ];
          authors = builtins.concatStringsSep "" (builtins.map (match: let
            name = builtins.elemAt match 0;
            email = builtins.elemAt match 1;
          in "\n    {name = \"${name}\", email = \"${email}\"},") (
            builtins.map
            (author-str: builtins.match "(.+) <(.+)>" author-str)
            (workspace.package.authors)
          ));
          version = workspace.package.version;
        };
        pname = "probe_py.generated";
        version = workspace.package.version;
        pyproject = true;
        build-system = [
          python.pkgs.flit-core
        ];
        pythonImportsCheck = [pname];
      };

    probe-cli = craneLib.buildPackage (individualCrateArgs
      // {
        pname = "probe-cli";
        cargoExtraArgs = "-p probe_cli";
      });
    probe-macros = craneLib.buildPackage (individualCrateArgs
      // {
        pname = "probe-macros";
        cargoExtraArgs = "-p probe_macros";
      });
  };
  checks = {
    probe-workspace-clippy = craneLib.cargoClippy (commonArgs
      // {
        inherit (packages) cargoArtifacts;
        cargoClippyExtraArgs = "--all-targets -- --deny warnings";
      });

    probe-workspace-doc = craneLib.cargoDoc (commonArgs
      // {
        inherit (packages) cargoArtifacts;
      });

    # Check formatting
    probe-workspace-fmt = craneLib.cargoFmt {
      inherit src;
    };

    # Audit dependencies
    probe-workspace-audit = craneLib.cargoAudit {
      inherit src advisory-db;
    };

    # Audit licenses
    probe-workspace-deny = craneLib.cargoDeny {
      inherit src;
    };

    # Run tests with cargo-nextest
    # this is why `doCheck = false` on the crate derivations, so as to not
    # run the tests twice.
    probe-workspace-nextest = craneLib.cargoNextest (commonArgs
      // {
        inherit (packages) cargoArtifacts;
        partitions = 1;
        partitionType = "count";
      });
  };
}
