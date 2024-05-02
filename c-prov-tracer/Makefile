CFLAGS=-Wno-cast-function-type -Wno-array-parameter -g -std=c11 -ldl -Wall -Wextra -fPIC -pthread

simple: simple.c
	gcc -g -Wall -Wextra simple.c -o simple

test-simple: libprov.so simple
	rm -rf .prov && env MALLOC_CHECK_=7 LD_PRELOAD=./libprov.so PROV_LOG_VERBOSE=1 head flake.nix && cat .prov/*

test-suite: libprov.so test.py
	python3.12 -m pytest test.py --maxfail=1 --capture=tee-sys --verbose

gdb: libprov.so
	gdb --quiet $$(which env) --args $$(which env) MALLOC_CHECK_=0 LD_PRELOAD=./libprov.so head flake.nix

valgrind: libprov.so simple
	valgrind --quiet --trace-children=yes --leak-check=full --track-origins=yes env MALLOC_CHECK_= LD_PRELOAD=./libprov.so head flake.nix

pdb: gen_libc_hooks.py libc_hooks_source.c
	python3.12 -m pdb gen_libc_hooks.py

libprov.so: *.c libc_hooks.c
	gcc $(CFLAGS) -shared -o $@ libprov.c

libc_hooks.c: gen_libc_hooks.py libc_hooks_source.c
	python3.12 gen_libc_hooks.py

clean:
	rm libprov.so libc_hooks.{c,h} simple

.PHONY: clean test debug
