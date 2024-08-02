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

check-mypy:
    mypy --strict --package probe_py.manual
    mypy --strict --package probe_py.generated
    mypy --strict probe_src/libprobe

compile-lib:
    make --directory=probe_src/libprobe all

compile-cli:
    env --chdir=probe_src/probe_frontend cargo build --release

compile: compile-lib compile-cli

test-ci: compile-libprobe
    make --directory=probe_src/tests/c all
    cd probe_src && python -m pytest .

test-dev: compile-libprobe
    make --directory=probe_src/tests/c all
    cd probe_src && python -m pytest . --failed-first --maxfail=1

check-flake:
    nix flake check --all-systems

pre-commit: fix-format-nix     fix-ruff compile-all check-mypy check-flake test-dev

on-push:    check-format-nix check-ruff compile-all check-mypy check-flake test-ci
