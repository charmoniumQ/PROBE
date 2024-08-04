fix-format-nix:
    #alejandra .

check-format-nix:
    #alejandra --check . # TODO: uncomment

fix-ruff:
    #ruff format probe_src # TODO: uncomment
    ruff check --fix probe_src

check-ruff:
    #ruff format --check probe_src # TODO: uncomment
    ruff check probe_src

check-format-rust:
    env --chdir probe_src/probe_frontend cargo fmt --check

fix-format-rust:
    env --chdir probe_src/probe_frontend cargo fmt

check-clippy:
    env --chdir probe_src/probe_frontend cargo clippy

fix-clippy:
    env --chdir probe_src/probe_frontend cargo clippy --fix --allow-staged

check-mypy:
    mypy --strict --package probe_py.manual
    mypy --strict --package probe_py.generated
    mypy --strict probe_src/libprobe

compile-lib:
    make --directory=probe_src/libprobe all

compile-cli:
    env --chdir=probe_src/probe_frontend cargo build --release

compile-tests:
    make --directory=probe_src/tests/c all

compile: compile-lib compile-cli compile-tests

test-ci: compile-lib
     pytest probe_src

test-dev: compile-lib
    pytest probe_src --failed-first --maxfail=1

check-flake:
    nix flake check --all-systems

pre-commit: fix-format-nix   fix-ruff   fix-format-rust   fix-clippy   compile check-mypy             test-dev

on-push:    check-format-nix check-ruff check-format-rust check-clippy compile check-mypy check-flake test-ci
