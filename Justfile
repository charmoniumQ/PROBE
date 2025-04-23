lint-nix:
    alejandra .

test-nix:
    nix build .#probe-bundled
    nix flake lint --all-systems

lint-py: compile-cli
    # fix-py depends on compile-cli for the autogen python code
    #ruff format probe_py/ tests/ libprobe/generator/ # TODO: uncomment
    ruff check --fix probe_py/ tests/ libprobe/generator/
    # dmypy == daemon mypy; much faster on subsequent iterations.
    dmypy run -- --strict --no-namespace-packages --pretty probe_py/ tests/ libprobe/generator/

[working-directory: 'cli-wrapper']
lint-cli:
    # cargo clippy refuses to run if unstaged inputs (fixes may be destructive)
    # so we git add -A
    git add -A
    cargo clippy --fix --allow-staged -- --deny warnings
    cargo fmt
    cargo doc --workspace
    cargo deny check
    cargo audit
    cargo hakari generate
    cargo hakari manage-deps

[working-directory: 'cli-wrapper']
compile-cli:
    cargo build
    cargo build --release

[working-directory: 'libprobe']
lint-lib:
    make format
    make check

[working-directory: 'libprobe']
compile-lib: compile-cli
    make all

[working-directory: 'tests/examples']
compile-tests:
    make all

lint: lint-py lint-cli lint-lib

compile: compile-cli compile-lib compile-tests

test: compile
    python -m pytest tests/ -ra --failed-first --maxfail=1 -v -W error

pre-commit: lint compile test
