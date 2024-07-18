SOURCE_VERSION ?= $(shell git rev-parse --short HEAD)
CFLAGS ?= -DSOURCE_VERSION=\"$(SOURCE_VERSION)\" -Wno-cast-function-type -Wno-array-parameter -ffreestanding -Wl,--as-needed -Wall -Wextra -pthread
DBGCFLAGS ?= $(CFLAGS) -Og -g
OPTCFLAGS ?= $(CFLAGS) -O3 -DNDEBUG
LIBCFLAGS ?= -fPIC -nostdlib -shared
SOURCE_FILES := $(wildcard src/*.c) $(wildcard include/*.h)

GENERATED_FILES := generated/libc_hooks.c generated/libc_hooks.h
ALL_TARGETS := build/libprobe-dbg.so build/libprobe.so

all: $(ALL_TARGETS)
.PHONY: all

build/lib%.so: $(SOURCE_FILES) $(GENERATED_FILES)
	mkdir --parents build/
	gcc $(OPTCFLAGS) $(LIBCFLAGS) -o $@ src/lib.c

build/lib%-dbg.so: $(SOURCE_FILES) $(GENERATED_FILES)
	mkdir --parents build/
	gcc $(DBGCFLAGS) $(LIBCFLAGS) -o $@ src/lib.c

$(GENERATED_FILES): $(wildcard generator/*)
	./generator/gen_libc_hooks.py

clean:
	mkdir --parents build/ generated/
	touch $(GENERATED_FILES) $(ALL_TARGETS)
	rm --force $(GENERATED_FILES) $(ALL_TARGETS)
.PHONY: clean
