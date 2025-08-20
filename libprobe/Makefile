CC ?= clang
LD ?= ld
VERSION ?= $(shell git rev-parse --short HEAD)
CFLAGS := \
    $(CFLAGS) \
    -DSOURCE_VERSION=\"$(VERSION)\" \
    -fvisibility=hidden \
    -Werror \
    -Wall -Wextra \
    -Wno-unused-command-line-argument \
    -fstrict-aliasing
# musl-clang wrapper triggers -Wno-unused-command-line-argument.
# But musl with clang (normal invocation) does not.

DBGCFLAGS := -Og -g       -fpic
OPTCFLAGS := -O3 -DNDEBUG -fPIC
GENERATED_SOURCE_FILES := generated/libc_hooks.c
GENERATED_HEADER_FILES := generated/libc_hooks.h
GENERATED_FILES := $(GENERATED_SOURCE_FILES) $(GENERATED_HEADER_FILES)
MANUAL_SOURCE_FILES := $(wildcard src/*.c)
MANUAL_HEADER_FILES := $(wildcard src/*.h) $(wildcard include/libprobe/*.h)
SOURCE_FILES := $(GENERATED_SOURCE_FILES) $(MANUAL_SOURCE_FILES)
HEADER_FILES := $(GENERATED_HEADER_FILES) $(MANUAL_HEADER_FILES)
TEST_FILES := $(wildcard tests/*.c)
BUILD_DIR := .build

all: compile_commands.json $(BUILD_DIR)/libprobe.so $(BUILD_DIR)/libprobe.dbg.so
.PHONY: all

tests: $(BUILD_DIR)/probe_libc_tests $(BUILD_DIR)/probe_libc_tests.dbg
.PHONY: tests

generated: $(GENERATED_FILES)
.PHONY: generated

$(BUILD_DIR)/libprobe.so: $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.o)) $(MAKEFILE_LIST)
	$(CC) -MJ $@.compile_command.json -flto    -fpic -shared -o $@ $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.o))

$(BUILD_DIR)/libprobe.dbg.so: $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.dbg.o)) $(MAKEFILE_LIST)
	$(CC) -MJ $@.compile_command.json -fno-lto -fPIC -shared -o $@ $(addprefix $(BUILD_DIR)/,$(SOURCE_FILES:.c=.dbg.o))

$(BUILD_DIR)/%.o: %.c $(HEADER_FILES) $(MAKEFILE_LIST)
	mkdir --parents $(dir $@)
	$(CC) -MJ $@.compile_command.json -c $(CFLAGS) $(OPTCFLAGS) -o $@ $<

$(BUILD_DIR)/%.dbg.o: %.c $(HEADER_FILES) $(MAKEFILE_LIST)
	mkdir --parents $(dir $@)
	$(CC) -MJ $@.compile_command.json -c $(CFLAGS) $(DBGCFLAGS) -o $@ $<

$(GENERATED_FILES): $(wildcard generator/*) $(MAKEFILE_LIST)
	mkdir --parents generated/
	python3 ./generator/gen_libc_hooks.py

compile_commands.json: $(BUILD_DIR)/libprobe.dbg.so
	echo '[' > $@
	env --chdir=$(BUILD_DIR) find . -name '*.compile_command.json' -exec cat '{}' \; >> $@
	echo ']' >> $@

$(BUILD_DIR)/undefined_symbols.txt: $(BUILD_DIR)/libprobe.dbg.so
	nm --dynamic .build/libprobe.dbg.so | grep ' U ' | sed 's/  */ /g' | cut --delim=' ' --fields=3 > $(BUILD_DIR)/undefined_symbols.txt

$(BUILD_DIR)/defined_symbols.txt: $(BUILD_DIR)/libprobe.dbg.so
	nm --dynamic .build/libprobe.dbg.so | grep ' T ' | cut --fields=3 --delimiter=' ' > $(BUILD_DIR)/defined_symbols.txt

$(BUILD_DIR)/probe_libc_tests: ./tests/probe_libc_units.c $(wildcard ./tests/probe_libc_units/*.c) ./src/probe_libc.c  $(MAKEFILE_LIST)
	$(CC) -MJ $@.compile_command.json -flto $(CFLAGS) $(OPTFLAGS) -o $@ -Isrc -lcriterion $<

$(BUILD_DIR)/probe_libc_tests.dbg: ./tests/probe_libc_units.c $(wildcard ./tests/probe_libc_units/*.c) ./src/probe_libc.c $(MAKEFILE_LIST)
	$(CC) -MJ $@.compile_command.json -fno-lto $(CFLAGS) $(DBGFLAGS) -o $@ -Isrc -lcriterion $<

check: compile_commands.json $(BUILD_DIR)/probe_libc_tests $(GENERATED_FILES)
	python3 ./sorted_symbol_versions.py .build/libprobe.dbg.so | tail --lines=5
	test GLIBC_2.34 = $(shell python3 ./sorted_symbol_versions.py .build/libprobe.dbg.so | tail --lines=1 | cut --fields=2 --delimiter=' ')
	clang-check --analyze -extra-arg -Xanalyzer -extra-arg -analyzer-output=text $(SOURCE_FILES)
	clang-format --dry-run --Werror $(MANUAL_SOURCE_FILES) $(MANUAL_HEADER_FILES)
	echo $(SOURCE_FILES) $(HEADER_FILES) | xargs --max-args 1 include-what-you-use -Xiwyu --error=1 -Wno-macro-redefined
	clang-tidy  $(SOURCE_FILES)
	python3 ./check_hooked_fns.py $(MANUAL_SOURCE_FILES)
	python3 ./check_needed_syms.py .build/libprobe.dbg.so .build/libprobe.so
	cppcheck    $(SOURCE_FILES) --check-level=exhaustive -UNDEBUG
	$(BUILD_DIR)/probe_libc_tests

#	cppclean    $(SOURCE_FILES)
# Currently, cppclean does not provide a mechanism to disable warnings.
# It flags *all* static data as a warning because it may not be threadsafe.
# I have carefully ensured our static data is either thread-local or guarded by a mutex (at initialization time)
# Nevertheless, selecting which warnings to flag is still a TODO in cppclean.
# https://github.com/myint/cppclean/blob/aa73d06022533a3ff0a956910f2df9a54c233d88/cpp/find_warnings.py#L18

# For some reason, include-what-you-use uses slightly different system headers and builtin definitions from Clang.
# It finds a "macro redefined" warning whenever we include stdint.h.
# Weird, but I'll just turn that off.
# We already check that compilation warning when we compile with Clang.

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
	mkdir --parents $(BUILD_DIR)/
	rm --force --recursive $(BUILD_DIR)/ $(GENERATED_FILES) compile_commands.json
.PHONY: clean

format:
# Yes, this clang-formats the generated sources
# But, they aren't checked into VCS, so I don't care
	git add --all .
	clang-format -i $(MANUAL_SOURCE_FILES) $(MANUAL_HEADER_FILES)
.PHONY: format

.SUFFIXES:
