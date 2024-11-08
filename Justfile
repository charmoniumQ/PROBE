fix-format-nix:
    alejandra .

fix-ruff:
    #ruff format probe_src # TODO: uncomment
    ruff check --fix probe_src

fix-format-rust:
    env --chdir probe_src/frontend cargo fmt

fix-clippy:
    git add -A
    env --chdir probe_src/frontend cargo clippy --fix --allow-staged

check-mypy:
    mypy --strict probe_src/libprobe
    mypy --strict --package probe_py.generated
    mypy --strict --package probe_py.manual

compile-lib:
    make --directory=libprobe all

compile-cli:
    env --chdir=cli-wrapper cargo build --release

compile-tests:
    make --directory=tests/c all

compile: compile-lib compile-cli compile-tests

test-dev: compile
    pytest probe_src --failed-first --maxfail=1

pre-commit: fix-format-nix fix-ruff fix-format-rust fix-clippy compile check-mypy test-dev
