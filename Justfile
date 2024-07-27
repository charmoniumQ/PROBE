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

check-clang:
    clang-tidy probe_src/**/*.{c,h} -- -Iinclude

compile-lib:
    make --directory=probe_src/libprobe all

compile-cli:
    env --chdir=probe_src/frontend cargo build --release

compile-tests:
    make --directory=probe_src/tests/c all

compile: compile-lib compile-cli compile-tests

test-dev: compile
    pytest probe_src --failed-first --maxfail=1

pre-commit: fix-format-nix fix-ruff fix-format-rust fix-clippy check-clang compile check-mypy test-dev

on-push: check-format-nix check-ruff check-mypy check-flake compile-libprobe test-ci
