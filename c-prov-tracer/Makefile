CFLAGS=-Wno-cast-function-type -Wno-array-parameter -g -std=c11 -ldl -Wall -Wextra -fPIC -pthread

# On some systems, /usr/bin/env is a script that invokes the "true" binary env. GDB needs the binary one.
# So we use the default-assignment operator ?=.
ENV ?= /usr/bin/env

TEST_SHELL_COMMAND ?= 'head -c 1 flake.nix && cd ..'
#TEST_SHELL_COMMAND ?= 'head -c 1 flake.nix && cd .. && head -c 1 tasks.org && echo && python -c "print(5)"'

ANALYZE_PROV_COMMAND = tree .prov

simple: simple.c
	gcc -g -Wall -Wextra simple.c -o simple

run-simple: libprov.so simple
	rm -rf .prov && env LD_PRELOAD=./libprov.so PROV_LOG_VERBOSE=1 ./simple flake.nix && $(ANALYZE_PROV_COMMAND)

run-head: libprov.so
	rm -rf .prov && env LD_PRELOAD=./libprov.so PROV_LOG_VERBOSE=1 head flake.nix && $(ANALYZE_PROV_COMMAND)

run-shell: libprov.so
	rm -rf .prov && $(ENV) PROV_LOG_VERBOSE=1 LD_PRELOAD=./libprov.so sh -c $(TEST_SHELL_COMMAND) && $(ANALYZE_PROV_COMMAND)

ltrace-shell: libprov.so
	rm -rf .prov && ltrace -f -s 1024 --output /dev/stderr $(ENV) sh -c $(TEST_SHELL_COMMAND) && $(ANALYZE_PROV_COMMAND)

test-suite: libprov.so test_suite.py
	python3 -m pytest test_suite.py --maxfail=1 --capture=tee-sys --verbose

gdb-head: libprov.so
	gdb --quiet --args $(ENV) PROV_LOG_VERBOSE=1 LD_PRELOAD=./libprov.so head flake.nix

gdb-simple: libprov.so simple
	gdb --quiet --args $(ENV) PROV_LOG_VERBOSE=1 LD_PRELOAD=./libprov.so ./simple flake.nix

gdb-shell: libprov.so
	setarch --addr-no-randomize gdb --quiet --args $(ENV) PROV_LOG_VERBOSE=1 LD_PRELOAD=./libprov.so sh -c $(TEST_SHELL_COMMAND)

valgrind: libprov.so simple
	valgrind --quiet --trace-children=yes --leak-check=full --track-origins=yes env MALLOC_CHECK_=0 LD_PRELOAD=./libprov.so head flake.nix

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
