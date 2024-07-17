format-nix:
    alejandra .

format-python:
    #black probe_src/probe_py

check-ruff:
    ruff check probe_src/probe_py

check-mypy:
    cd probe_src
    mypy --package probe_py --strict

test:
    #cd probe_src
    #make --directory=libprobe all
    #python -m pytest .

test-dev:
    cd probe_src
    make --directory=libprobe all
    python -m pytest . --failed-first --maxfail=1

flake-check:
    nix flake check --all-systems
