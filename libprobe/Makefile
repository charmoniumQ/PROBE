CC ?= clang
CFLAGS := $(CFLAGS) -DSOURCE_VERSION=\"$(shell git rev-parse --short HEAD)\" -fvisibility=hidden -Werror -Wall -Wextra
DBGCFLAGS := -Og -g       -fpic
OPTCFLAGS := -O3 -DNDEBUG -fPIC
GENERATED_SOURCE_FILES := generated/libc_hooks.c
GENERATED_HEADER_FILES := generated/libc_hooks.h
GENERATED_FILES := $(GENERATED_SOURCE_FILES) $(GENERATED_HEADER_FILES)
SOURCE_FILES := $(wildcard src/*.c) $(GENERATED_SOURCE_FILES)
HEADER_FILES := $(wildcard src/*.h) $(GENERATED_HEADER_FILES)
BUILD_DIR := .build/

all: $(BUILD_DIR)/libprobe.so $(BUILD_DIR)/libprobe.dbg.so
.PHONY: all

$(BUILD_DIR)/libprobe.so: $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.o)) $(MAKEFILE_LIST)
	$(CC) -flto    -fpic -shared -o $@ $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.o))

$(BUILD_DIR)/libprobe.dbg.so: $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.dbg.o)) $(MAKEFILE_LIST)
	$(CC) -fno-lto -fPIC -shared -o $@ $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.dbg.o))

$(BUILD_DIR)/%.o: %.c $(HEADER_FILES) $(MAKEFILE_LIST)
	mkdir --parents $(dir $@)
	$(CC) -c $(CFLAGS) $(OPTCFLAGS) -o $@ $<

$(BUILD_DIR)/%.dbg.o: %.c $(HEADER_FILES) $(MAKEFILE_LIST)
	mkdir --parents $(dir $@)
	$(CC) -c $(CFLAGS) $(DBGCFLAGS) -o $@ $<

$(GENERATED_FILES): $(wildcard generator/*) $(MAKEFILE_LIST)
	mkdir --parents generated/
	python3 ./generator/gen_libc_hooks.py

install:
	mkdir --parents $(INSTALL_PREFIX)
	install -D --target-directory $(INSTALL_PREFIX)/lib/ $(BUILD_DIR)/libprobe.so $(BUILD_DIR)/libprobe.dbg.so
.PHONY: install

clean:
	mkdir --parents $(BUILD_DIR)/ generated/
	rm --force --recursive $(BUILD_DIR)/ generated/
.PHONY: clean

.SUFFIXES:
