{
  pkgs,
  craneLib,
  rust-target,
  advisory-db,
  system,
  python,
  lib,
}: rec {
  # See https://crane.dev/examples/quick-start-workspace.html

  src = craneLib.cleanCargoSource ./.;

  # Common arguments can be set here to avoid repeating them later
  commonArgs = {
    inherit src;
    strictDeps = true;

    # all the crates in this workspace either use rust-bindgen or depend
    # on local crate that does.
    nativeBuildInputs = [
      pkgs.rustPlatform.bindgenHook
    ];

    CARGO_BUILD_TARGET = rust-target;
    CARGO_BUILD_RUSTFLAGS = "-C target-feature=+crt-static";
    CPATH = ../libprobe/include;
  };

  # Build *just* the cargo dependencies (of the entire workspace),
  # so we can reuse all of that work (e.g. via cachix) when running in CI
  # It is *highly* recommended to use something like cargo-hakari to avoid
  # cache misses when building individual top-level-crates
  cargoArtifacts = craneLib.buildDepsOnly commonArgs;

  individualCrateArgs =
    commonArgs
    // {
      inherit cargoArtifacts;
      inherit (craneLib.crateNameFromCargoToml {inherit src;}) version;
      # disable tests since we'll run them all via cargo-nextest
      doCheck = false;
    };

  fileSetForCrate = crate: lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./Cargo.toml
      ./Cargo.lock
      (craneLib.fileset.commonCargoSources crate)
    ];
  };

  packages = rec {
    inherit cargoArtifacts;

    # Build the top-level crates of the workspace as individual derivations.
    # This allows consumers to only depend on (and build) only what they need.
    # Though it is possible to build the entire workspace as a single derivation,
    # so this is left up to you on how to organize things
    probe-lib = craneLib.buildPackage (individualCrateArgs
      // {
        pname = "probe-lib";
        cargoExtraArgs = "-p probe_lib";
        src = fileSetForCrate ./crates/lib;
      });

    probe-cli = craneLib.buildPackage (individualCrateArgs
      // {
        pname = "probe-cli";
        cargoExtraArgs = "-p probe_cli";
        src = fileSetForCrate ./crates/cli;
      });
    probe-macros = craneLib.buildPackage (individualCrateArgs
      // {
        pname = "probe-macros";
        cargoExtraArgs = "-p probe_macros";
        src = fileSetForCrate ./crates/macros;
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
