lint-nix:
    alejandra .

test-nix:
    nix build .#probe-bundled
    nix flake check --all-systems

lint-py: update-headers-py
    # fix-py depends on compile-cli for the autogen python code
    #ruff format probe_py/ tests/ libprobe/generator/ # TODO: uncomment
    ruff check --fix probe_py/ tests/ libprobe/generator/
    # dmypy == daemon mypy; much faster on subsequent iterations.
    dmypy run -- --strict --no-namespace-packages --pretty probe_py/ tests/ libprobe/generator/

[working-directory: 'cli-wrapper']
clean-cli:
    cargo clean

[working-directory: 'cli-wrapper']
lint-cli:
    # cargo clippy refuses to run if unstaged inputs (fixes may be destructive)
    # so we git add -A
    git add -A .
    cargo clippy --fix --allow-staged --allow-dirty -- --deny warnings
    cargo fmt
    cargo doc --workspace
    cargo deny check
    cargo audit
    cargo hakari generate
    cargo hakari manage-deps
    cargo test

[working-directory: 'cli-wrapper']
compile-cli:
    cargo build
    cargo run --bin probe_headers

[working-directory: 'probe_py']
update-headers-py: compile-cli
    ./generate_headers.py

# https://datamodel-code-generator.koxudaxi.dev/type-mappings/
# --use-root-model-type-alias¶

[working-directory: 'libprobe']
clean-lib:
    make clean

[working-directory: 'libprobe']
lint-lib:
    make format
    make check

[working-directory: 'libprobe']
test-lib:
    make tests

[working-directory: 'libprobe']
compile-lib: compile-cli
    make all

[working-directory: 'tests/examples']
clean-tests:
    make clean

[working-directory: 'tests/examples']
compile-tests:
    make all

clean: clean-cli clean-lib clean-tests

lint: lint-py lint-cli lint-lib lint-nix

compile: compile-cli compile-lib compile-tests update-headers-py

test: compile
    python -m pytest -c tests/pytest.ini

pre-commit: lint compile test
