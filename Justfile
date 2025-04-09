fix-nix:
    alejandra .

fix-py: compile-cli
    # fix-py depends on compile-cli for the autogen python code
    #ruff format probe_py/ tests/ libprobe/generator/ # TODO: uncomment
    ruff check --fix probe_py/ tests/ libprobe/generator/

[working-directory('cli-wrapper')]
fix-cli:
    # cargo clippy refuses to run if unstaged inputs (fixes may be destructive)
    # so we git add -A
    git add -A
    cargo clippy --fix --allow-staged -- --deny warnings
    cargo fmt

fix: fix-nix fix-py fix-cli

check-py: compile-cli
    # dmypy == daemon mypy; much faster on subsequent iterations.
    dmypy run -- --strict --no-namespace-packages --pretty probe_py/ tests/ libprobe/generator/

[working-directory('cli-wrapper')]
check-cli:
    cargo doc --workspace

check: check-py check-cli check-lib

[working-directory: 'libprobe']
compile-lib:
    make all

[working-directory('libprobe')]
check-lib:
    make check

[working-directory: 'cli-wrapper']
compile-cli:
    cargo build --release
    cargo build

[working-directory: 'tests/examples']
compile-tests:
    make all

compile: compile-lib compile-cli compile-tests

test-nix:
    nix build .#probe-bundled
    nix flake check --all-systems

test-native: compile
    python -m pytest tests/ -ra --failed-first --maxfail=1 -v

test: test-native
# Unless you the user explicitly asks (`just test-nix`),
# we don't really need to test-nix.
# It runs the same checks as `just test` and `just check`, but in Nix.

pre-commit: fix check compile test
