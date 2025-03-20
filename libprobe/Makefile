CC ?= gcc
SOURCE_VERSION ?= $(shell git rev-parse --short HEAD)
CFLAGS ?= -DSOURCE_VERSION=\"$(SOURCE_VERSION)\" -Werror -Wall -Wextra -fvisibility=internal -ldl -pthread
DBGCFLAGS ?= -Og -g -fPIC
OPTCFLAGS ?= -O3 -DNDEBUG -fpic

GENERATED_SOURCE_FILES := generated/libc_hooks.c
GENERATED_HEADER_FILES := generated/libc_hooks.h
GENERATED_FILES := $(GENERATED_SOURCE_FILES) $(GENERATED_HEADER_FILES)
SOURCE_FILES := $(wildcard src/*.c) $(GENERATED_SOURCE_FILES)
HEADER_FILES := $(wildcard src/*.h) $(GENERATED_HEADER_FILES)
ALL_TARGETS := build/libprobe.dbg.so build/libprobe.so

build/%.o: %.c $(HEADER_FILES)
	mkdir --parents $(dir $@)
	$(CC) -c $(CFLAGS) $(OPTCFLAGS) -o $@ $<

build/%.dbg.o: %.c $(HEADER_FILES)
	mkdir --parents $(dir $@)
	$(CC) -c $(CFLAGS) $(DBGCFLAGS) -o $@ $<

build/libprobe.so: $(addprefix build/,$(SOURCE_FILES:.c=.o))
	$(CC) -flto -fpic -shared -o $@ $^

build/libprobe.dbg.so: $(addprefix build/,$(SOURCE_FILES:.c=.dbg.o))
	$(CC) -fPIC -shared -o $@ $^

all: build/libprobe.so build/libprobe.dbg.so

$(GENERATED_FILES): $(wildcard generator/*)
	mkdir --parents generated/
	python3 ./generator/gen_libc_hooks.py

install:
	mkdir --parents $(INSTALL_PREFIX)
	install -D --target-directory $(INSTALL_PREFIX)/lib/ build/lib*.so

clean:
	mkdir --parents build/ generated/
	touch $(GENERATED_FILES) $(ALL_TARGETS)
	rm --force $(GENERATED_FILES) $(ALL_TARGETS)
.PHONY: clean

.SUFFIXES:
