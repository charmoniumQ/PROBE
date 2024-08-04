CFLAGS ?= -Wall -Wextra -Og -g

test: test_arena parse_arena.py
	./test_arena && ./parse_arena.py arena_data > /dev/null && tar --create --file arena_data.tar arena_data && ./parse_arena.py arena_data.tar arena_data/ > /dev/null
.PHONY: test

clean:
	touch test_arena arena_data && rm --force --recursive test_arena arena_data
.PHONY: clean
