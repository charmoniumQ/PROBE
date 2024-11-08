 UNAME_S := $(shell uname -s)

SOURCE_VERSION ?= $(shell git rev-parse --short HEAD)
CFLAGS_COMMON ?= -DSOURCE_VERSION=\"$(SOURCE_VERSION)\" -Wall -Wextra -pthread -fPIC $(NIX_CFLAGS_COMPILE)
DBGCFLAGS ?= -Og -g
OPTCFLAGS ?= -O3 -DNDEBUG

ifeq ($(UNAME_S),Linux)
    LIB_EXTENSION = so
    SHARED_LIB_FLAGS = -shared
    EXTRA_LIBS = -ldl
    INSTALL_CMD = install -D --target-directory $(INSTALL_PREFIX)/lib/ build/lib*.$(LIB_EXTENSION)
    MKDIR_CMD = mkdir --parents
else ifeq ($(UNAME_S),Darwin)
    LIB_EXTENSION = dylib
    SHARED_LIB_FLAGS = -dynamiclib
    EXTRA_LIBS =
    INSTALL_CMD = install -d $(INSTALL_PREFIX)/lib/ && install build/lib*.$(LIB_EXTENSION) $(INSTALL_PREFIX)/lib/
    MKDIR_CMD = mkdir -p
else
    $(error Unsupported OS: $(UNAME_S))
endif

SOURCE_FILES := $(wildcard src/*.c) $(wildcard include/*.h)
GENERATED_FILES := generated/libc_hooks.c generated/libc_hooks.h
ALL_TARGETS := build/libprobe-dbg.$(LIB_EXTENSION) build/libprobe.$(LIB_EXTENSION)

all: $(ALL_TARGETS)
.PHONY: all

build/lib%.$(LIB_EXTENSION): $(SOURCE_FILES) $(GENERATED_FILES)
	$(MKDIR_CMD) build
	gcc $(CFLAGS_COMMON) $(OPTCFLAGS) $(SHARED_LIB_FLAGS) $(EXTRA_LIBS) -o $@ src/lib.c

build/lib%-dbg.$(LIB_EXTENSION): $(SOURCE_FILES) $(GENERATED_FILES)
	$(MKDIR_CMD) build
	gcc $(CFLAGS_COMMON) $(DBGCFLAGS) $(SHARED_LIB_FLAGS) $(EXTRA_LIBS) -o $@ src/lib.c

$(GENERATED_FILES): $(wildcard generator/*)
	./generator/gen_libc_hooks.py $(UNAME_S)

install:
	$(INSTALL_CMD)

clean:
	$(MKDIR_CMD) build/ generated/
	touch $(GENERATED_FILES) $(ALL_TARGETS)
	rm --force $(GENERATED_FILES) $(ALL_TARGETS)
.PHONY: clean
