format-nix:
    alejandra .

format-python:
    black probe_src/probe_py

check-ruff:
    ruff check probe_src/probe_py

check-mypy:
    (cd probe_src && mypy --package probe_py --strict)

test:
    python -m pytest probe_src/probe_py

test-dev:
    python -m pytest probe_src/probe_py --failed-first --maxfail=1

flake-check:
    nix flake check --all-systems
