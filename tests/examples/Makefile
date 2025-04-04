# Can use this to test ASAN, as claimed in the paper
#
#     make all "CFLAGS=-Wall -Wextra -Og -g -fsanitize=address"
#     env ASAN_OPTIONS=verify_asan_link_order=0 probe record -f ./createFile.exe
#
# Subsequently, note whether the machine exploded.
# If not, then PROBE does not interfere with ASAN.

CC ?= gcc
CFLAGS ?= -Wall -Wextra -Og -g

SOURCE_FILES := $(wildcard *.c)

all: $(filter-out minimal_libprobe.exe,$(SOURCE_FILES:.c=.exe)) minimal_libprobe.so

%.exe: %.c
	$(CC) $(CFLAGS) -o $@ $<

%.so: %.c
	$(CC) $(CFLAGS) -fpic -shared -o $@ $<

clean:
	touch $(SOURCE_FILES:.c=.so) $(SOURCE_FILES:.c=.exe) && rm --force $(SOURCE_FILES:.c=.so) $(SOURCE_FILES:.c=.exe)
.PHONY: clean
