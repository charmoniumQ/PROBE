CFLAGS=-Wno-cast-function-type -g -std=c11 -ldl -Wall -Wextra -nostdlib -nodefaultlibs -fPIC

test: libprov.so test.py
	python3.12 -m pytest test.py

debug-run: libprov.so
	gdb $$(which env) --args $$(which env) LD_PRELOAD=./libprov.so head flake.nix

debug-codegen: gen_libprov.py libc_subset.c
	python3.12 -m pdb gen_libprov.py

libprov.so: libprov.c libprov_prefix.c libprov_middle.c libprov_suffix.c
	gcc $(CFLAGS)  -shared -o $@ $<

libprov_middle.c: gen_libprov.py libc_subset.c
	python3.12 gen_libprov.py > libprov_middle.c

clean:
	rm libprov.so libprov_middle.c

.PHONY: clean test debug
