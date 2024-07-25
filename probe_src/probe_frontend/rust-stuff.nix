{
  self,
  pkgs,
  crane,
  flake-utils,
  advisory-db,
  rust-overlay,
  system,
  ...
}:
let
    systems = {
      # "nix system" = "rust target";
      "x86_64-linux" = "x86_64-unknown-linux-musl";
      "i686-linux" = "i686-unknown-linux-musl";
      "aarch64-linux" = "aarch64-unknown-linux-musl";
      "armv7l-linux" = "armv7-unknown-linux-musleabi";
    };
      craneLib = (crane.mkLib pkgs).overrideToolchain (p:
        p.rust-bin.stable.latest.default.override {
          targets = [systems.${system}];
        });

      src = ./.;

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
          mkdir -p ./python
          export PYGEN_OUTFILE="$(realpath ./python/probe_py/generated/ops.py)"
        '';

        LIBPROBE_INTERFACE = self.packages.${system}.libprobe-interface;

        CARGO_BUILD_TARGET = systems.${system};
        CARGO_BUILD_RUSTFLAGS = "-C target-feature=+crt-static";
      };

      # Build *just* the cargo dependencies (of the entire workspace),
      # so we can reuse all of that work (e.g. via cachix) when running in CI
      # It is *highly* recommended to use something like cargo-hakari to avoid
      # cache misses when building individual top-level-crates
      cargoArtifacts = craneLib.buildDepsOnly commonArgs;

      individualCrateArgs =
        commonArgs
        // {
          # inherit cargoArtifacts;
          inherit (craneLib.crateNameFromCargoToml {inherit src;}) version;
          # disable tests since we'll run them all via cargo-nextest
          doCheck = false;
        };

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
      probe-py-generated-src = pkgs.substituteAllFiles rec {
        name = "probe-py-${version}";
        src = probe-frontend;
        files = [
          "./pyproject.toml"
          "./LICENSE"
          "./probe_py/generated/__init__.py"
          "./probe_py/generated/ops.py"
          "./probe_py/generated/probe.py"
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
    in
      pkgs.python312.pkgs.buildPythonPackage rec {
        pname = "probe_py.generated";
        version = probe-py-generated-src.version;
        pyproject = true;
        build-system = [
          pkgs.python312Packages.flit-core
        ];
        unpackPhase = ''
          cp --recursive ${probe-py-generated-src}/* /build
          cat /build/pyproject.toml
        '';
        pythonImportsCheck = [ pname ];
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
    in {
      checks = {
        # Build the crates as part of `nix flake check` for convenience
        inherit probe-frontend probe-py-generated probe-cli probe-macros;

        # Run clippy (and deny all warnings) on the workspace source,
        # again, reusing the dependency artifacts from above.
        #
        # Note that this is done as a separate derivation so that
        # we can block the CI if there are issues here, but not
        # prevent downstream consumers from building our crate by itself.
        probe-workspace-clippy = craneLib.cargoClippy (commonArgs
          // {
            inherit cargoArtifacts;
            cargoClippyExtraArgs = "--all-targets -- --deny warnings";
          });

        probe-workspace-doc = craneLib.cargoDoc (commonArgs
          // {
            inherit cargoArtifacts;
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
            inherit cargoArtifacts;
            partitions = 1;
            partitionType = "count";
          });

      };

      packages = {
        inherit probe-cli probe-py-generated probe-macros;
      };

      devShells.default = craneLib.devShell {
        # Inherit inputs from checks.
        checks = self.checks.${system};

        shellHook = ''
          export __PROBE_LIB="$(realpath ../libprobe/build)"
          export PYGEN_OUTFILE="$(realpath ./python/probe_py/generated/ops.py)"
        '';

        packages = [
          pkgs.cargo-audit
          pkgs.cargo-expand
          pkgs.cargo-flamegraph
          pkgs.cargo-watch
          pkgs.gdb
          pkgs.rust-analyzer
        ];
      };
    }
