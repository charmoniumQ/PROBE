# Can use this to test ASAN, as claimed in the paper
#
#     make all "CFLAGS=-Wall -Wextra -Og -g -fsanitize=address"
#     env ASAN_OPTIONS=verify_asan_link_order=0 probe record -f ./createFile.exe
#
# Subsequently, note whether the machine exploded.
# If not, then PROBE does not interfere with ASAN.

CFLAGS ?= -Wall -Wextra -Og -g

SOURCE_FILES := $(wildcard *.c)

all: $(SOURCE_FILES:.c=.exe)

%.exe: %.c
	gcc $(CFLAGS) -o $@ $<

%.exe: %.s
	gcc $(CFLAGS) -o $@ $<

clean:
	touch $(SOURCE_FILES:.c=.exe) && rm --force $(SOURCE_FILES:.c=.exe)
.PHONY: clean
