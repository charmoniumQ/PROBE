CFLAGS=-Wno-cast-function-type -Wno-array-parameter -g -std=c11 -ldl -Wall -Wextra -nostdlib -nodefaultlibs -fPIC

test-raw: libprov.so
	rm -rf .prov && env MALLOC_CHECK_=7 LD_PRELOAD=./libprov.so LIBPROV_DIR=.prov/ bash -c 'head flake.nix' && cat .prov/*

test-suite: libprov.so test.py
	python3.12 -m pytest test.py

gdb: libprov.so
	gdb --quiet $$(which env) --args $$(which env) LD_PRELOAD=./libprov.so ls -l

valgrind: libprov.so
	valgrind --track-origins=yes --keep-stacktraces=alloc-and-free $$(which env) LD_PRELOAD=./libprov.so head flake.nix


pdb: gen_libc_hooks.py libc_hooks_source.c
	python3.12 -m pdb gen_libc_hooks.py

libprov.so: *.c
	gcc $(CFLAGS) -shared -o $@ libprov.c

libc_hooks.c: gen_libc_hooks.py libc_hooks_source.c
	python3.12 gen_libc_hooks.py

clean:
	rm libprov.so libc_hooks.{c,h}

.PHONY: clean test debug
