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

    # pygen needs to know where to write the python file
    preConfigurePhases = [
      "pygenConfigPhase"
    ];
    pygenConfigPhase = ''
      export PYGEN_OUTFILE="$out/resources/ops.py"
      mkdir --parents "$(dirname "$PYGEN_OUTFILE")"
      echo "Sending python code to $PYGEN_OUTFILE"
    '';
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

  fileSetForCrate = crates: lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions ([
      ./Cargo.toml
      ./Cargo.lock
    ] ++ (builtins.map craneLib.fileset.commonCargoSources crates));
  };

  packages = rec {
    inherit cargoArtifacts;

    # Prior to this version, the old code had one derivatino per crate (probe-cli, probe-lib, and probe-macros).
    # What could go wrong?
    # Since the old version used `src = ./.`, it would rebuild all three if any one changed.

    # craneLib's workspace example [1] says to use `src = fileSetForCrate ./path/to/crate`.
    # However, when I tried doing that, it would say "failed to load manifest for workspace member lib" because "failed to read macros/Cargo.toml".
    # Because `lib/Cargo.toml` has a dependency on `{path = "../macros"}`,
    # I think the source code of both crates have to be present at build-time of lib.
    # Which means no source filtering is possible.
    # Indeed the exposed packages in craneLib's example (my-cli and my-server) [1] do not depend on each other.
    # They depend on my-common, which is *not* filtered out (*is* included) in the `src` for those crates.
    # If it's possible to simultaneously:
    #   - expose two Cargo crates A and B
    #   - where A depends on B
    #   - when A changes only A needs to be rebuilt
    # then I don't know how to do it.
    # Therefore, I will only offer one crate as a Nix package.
    #
    # https://crane.dev/examples/quick-start-workspace.html

    probe-cli = craneLib.buildPackage (individualCrateArgs
      // {
        pname = "probe-cli";
        cargoExtraArgs = "-p probe_cli";
        src = fileSetForCrate [
          ./cli
          ./lib
          ./macros
        ];
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
