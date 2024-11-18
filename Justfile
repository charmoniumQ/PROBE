fix-nix:
    alejandra .

fix-py:
    #ruff format probe_py/ tests/ libprobe/generator/ # TODO: uncomment
    ruff check --fix probe_py probe_py/ tests/ libprobe/generator/

fix-cli:
    # stage because cargo clippy fix may be destructive
    env --chdir cli-wrapper git add -A
    env --chdir cli-wrapper cargo clippy --fix --allow-staged -- --deny warnings
    env --chdir cli-wrapper cargo fmt

fix: fix-nix fix-py fix-cli

check-py:
    # dmypy == daemon mypy; much faster.
    dmypy run -- --strict --no-namespace-packages --pretty probe_py/ tests/ libprobe/generator/

check-cli:
    env --chdir cli-wrapper cargo doc --workspace

check: check-py check-cli

compile-lib:
    make --directory=libprobe all

compile-cli:
    env --chdir=cli-wrapper cargo build --release
    env --chdir=cli-wrapper cargo build

compile-tests:
    make --directory=tests/examples all

compile: compile-lib compile-cli compile-tests

test: compile
    python -m pytest tests/ -ra --failed-first --maxfail=1 -v

pre-commit: fix check compile test
