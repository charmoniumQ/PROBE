

# On some systems, /usr/bin/env is a script that invokes the "true" binary env. GDB needs the binary one.
# So we use the default-assignment operator ?=.
ENV ?= /usr/bin/env

#TEST_SHELL_COMMAND ?= 'head -c 1 flake.nix && cd ..'
TEST_SHELL_COMMAND ?= 'head -c 1 flake.nix && cd .. && head -c 1 tasks.org && echo'

ANALYZE_PROV_COMMAND = python parse_prov_log_dir.py

simple: simple.c
	gcc -g -Wall -Wextra simple.c -o simple

test-suite: libprov.so test_suite.py
	python3 -m pytest test_suite.py --maxfail=1 --capture=tee-sys --verbose

pdb: gen_libc_hooks.py libc_hooks_source.c
	python3 -m pdb gen_libc_hooks.py

libprov.so: *.c *.h libc_hooks.c
	gcc $(CFLAGS) -shared -o $@ libprov.c

libc_hooks.c: gen_libc_hooks.py libc_hooks_source.c
	python3 gen_libc_hooks.py

TARGETS = libprov.so libc_hooks.c libc_hooks.h simple __pycache__ .pytest_cache .mypy_cache .prov
clean:
	touch $(TARGETS) && rm -rf $(TARGETS)

.PHONY: clean run-simple run-head run-all gdb-simple gdb-head
