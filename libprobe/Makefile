CC ?= clang
VERSION ?= $(shell git rev-parse --short HEAD)
CFLAGS := \
    $(CFLAGS) \
    -DSOURCE_VERSION=\"$(VERSION)\" \
    -fvisibility=hidden \
    -Werror \
    -Wall -Wextra \
    -Wno-unused-command-line-argument \
    -fstrict-aliasing
DBGCFLAGS := -Og -g       -fpic
OPTCFLAGS := -O3 -DNDEBUG -fPIC
GENERATED_SOURCE_FILES := generated/libc_hooks.c
GENERATED_HEADER_FILES := generated/libc_hooks.h
GENERATED_FILES := $(GENERATED_SOURCE_FILES) $(GENERATED_HEADER_FILES)
MANUAL_SOURCE_FILES := $(wildcard src/*.c)
MANUAL_HEADER_FILES := $(wildcard src/*.h) $(wildcard include/libprobe/*.h)
SOURCE_FILES := $(GENERATED_SOURCE_FILES) $(MANUAL_SOURCE_FILES)
HEADER_FILES := $(GENERATED_HEADER_FILES) $(MANUAL_HEADER_FILES)
BUILD_DIR := .build

all: compile_commands.json $(BUILD_DIR)/libprobe.so $(BUILD_DIR)/libprobe.dbg.so
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

compile_commands.json: $(MAKEFILE_LIST)
	$(MAKE) clean
	$(MAKE) $(BUILD_DIR)/libprobe.dbg.so --dry-run | compiledb
# compiledb is better than bear.
# For bear, you have to actually run the compile.
# For compiledb, you can just dry-run.

$(BUILD_DIR)/defined_symbols.txt: $(BUILD_DIR)/libprobe.dbg.so
	nm --dynamic .build/libprobe.dbg.so | grep ' U ' | sed 's/  */ /g' | cut --delim=' ' --fields=3 > $(BUILD_DIR)/undefined_symbols.txt

$(BUILD_DIR)/undefined_symbols.txt: $(BUILD_DIR)/libprobe.dbg.so
	nm --dynamic .build/libprobe.dbg.so | grep ' T ' | cut --fields=3 --delimiter=' ' > $(BUILD_DIR)/defined_symbols.txt

check: compile_commands.json $(GENERATED_FILES)
	clang-format --dry-run --Werror $(MANUAL_SOURCE_FILES) $(MANUAL_HEADER_FILES)
	clang-check $(SOURCE_FILES)
	clang-tidy  $(SOURCE_FILES)
	cppcheck    $(SOURCE_FILES) --check-level=exhaustive -UNDEBUG
#	cppclean    $(SOURCE_FILES) # see libprobe/README.md
.PHONY: check

deep-check:
	$(MAKE) clean
	scan-build $(MAKE) $(BUILD_DIR)/libprobe.dbg.so
.PHONY: deep-check

install:
	mkdir --parents $(INSTALL_PREFIX)
	install -D --target-directory $(INSTALL_PREFIX)/lib/ $(BUILD_DIR)/libprobe.so $(BUILD_DIR)/libprobe.dbg.so
.PHONY: install

clean:
	mkdir --parents $(BUILD_DIR)/ generated/
	rm --force --recursive $(BUILD_DIR)/ generated/ compile_commands.json
.PHONY: clean

format:
# Yes, this clang-formats the generated sources
# But, they aren't checked into VCS, so I don't care
	git add --all .
	clang-format -i $(MANUAL_SOURCE_FILES) $(MANUAL_HEADER_FILES)
.PHONY: format

.SUFFIXES:
