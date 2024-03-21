test: libprov.so
	LD_PRELOAD=$(PWD)/libprov.so head flake.nix

.PHONY: test

libprov.so: libprov.c libprov_prefix.c libprov_middle.c libprov_suffix.c
	gcc -g -std=c11 -fPIC -shared -o $@ $< -ldl -Wall -Wextra -nostdlib -nodefaultlibs

libprov_middle.c: gen_libprov.py libc_subset.c
	python3.12 gen_libprov.py > libprov_middle.c

clean:
	rm libprov.so libprov_middle.c
