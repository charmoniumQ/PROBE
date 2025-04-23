CFLAGS ?= -Wall -Wextra -Og -g

SOURCE_FILES := $(wildcard *.c)

all: $(SOURCE_FILES:.c=.exe)

%.exe: %.c
	gcc $(CFLAGS) -o $@ $<

run: tls_after_fork.exe
	./tls_after_fork.exe
	./test_basic_libprobe.sh

clean:
	touch $(SOURCE_FILES:.c=.exe) && rm --force $(SOURCE_FILES:.c=.exe)
.PHONY: clean
