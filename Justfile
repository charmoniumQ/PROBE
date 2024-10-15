fix-format-nix:
    alejandra .

check-format-nix:
    alejandra --check .

fix-ruff:
    #ruff format probe_src # TODO: uncomment
    ruff check --fix probe_src

check-ruff:
    #ruff format --check probe_src # TODO: uncomment
    ruff check probe_src

check-format-rust:
    env --chdir probe_src/frontend cargo fmt --check

fix-format-rust:
    env --chdir probe_src/frontend cargo fmt

check-clippy:
    env --chdir probe_src/frontend cargo clippy

fix-clippy:
    git add -A
    env --chdir probe_src/frontend cargo clippy --fix --allow-staged

check-mypy:
    mypy --strict --package probe_py.manual
    mypy --strict --package probe_py.generated
    mypy --strict probe_src/libprobe

compile-lib:
    make --directory=probe_src/libprobe all

compile-cli:
    env --chdir=probe_src/frontend cargo build --release

compile-tests:
    make --directory=probe_src/tests/c all

compile: compile-lib compile-cli compile-tests

test-ci: compile
     pytest probe_src

test-dev: compile
    pytest probe_src --failed-first --maxfail=1

check-flake:
    nix flake check --all-systems

user-facing-build:
    # `just compile` is great, but it's the _dev-facing_ build.
    # Users will build PROBE following the `README.md`
    # which says `nix profile install github:charmoniumQ/PROBE#probe-bundled`
    # Which should be equivalent to this:
    nix build .#probe-bundled

pre-commit: fix-format-nix   fix-ruff   fix-format-rust   fix-clippy compile check-mypy test-dev
on-push:  check-format-nix check-ruff check-format-rust check-clippy compile check-mypy test-ci check-flake user-facing-build
