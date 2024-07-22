fix-format-nix:
    #alejandra .

check-format-nix:
    #alejandra --check .

fix-ruff:
    #ruff format probe_src
    ruff check --fix probe_src

check-ruff:
    #ruff format --check probe_src
    ruff check probe_src

check-mypy:
    MYPYPATH=probe_src mypy --strict --package arena
    MYPYPATH=probe_src mypy --strict --package probe_py
    mypy --strict probe_src/libprobe

compile-libprobe:
    make --directory=probe_src/libprobe all

test-ci: compile-libprobe
    make --directory=probe_src/tests/c all
    #cd probe_src && python -m pytest .

test-dev: compile-libprobe
    make --directory=probe_src/tests/c all
    #cd probe_src && python -m pytest . --failed-first --maxfail=1

check-flake:
    nix flake check --all-systems

pre-commit: fix-format-nix fix-ruff check-mypy check-flake compile-libprobe test-dev

on-push: check-format-nix check-ruff check-mypy check-flake compile-libprobe test-ci
