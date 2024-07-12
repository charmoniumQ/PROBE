format-nix:
    alejandra .

format-python:
    black probe_src/probe_py

check-ruff:
    ruff check probe_src/probe_py

check-mypy:
    (cd probe_src && mypy --package probe_py --strict)

test:
    pytest probe_src/probe_py

test-dev:
    pytest probe_src/probe_py --failed-first --maxfail=1

