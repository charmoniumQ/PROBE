# Directory of memory-mapped arenas

An [Arena allocator](https://en.wikipedia.org/wiki/Region-based_memory_management?oldformat=true) is a memory-allocation algorithm that allocates from the beginning of one big block of memory (called the arena).

In this library, each arena is memory mapped (`mmap`), so we don't have to explicitly save the arena to disk; everything written or mem-copied there persists automatically.

An ArenaDir is a group of arenas that automatically allocates a new Arena if the requested allocation is bigger than the free-space in the current Arena.

This may be especially useful for logging data; just copy memory over there or construct log records in place.

The ArenaDir can be parsed with `parse_arena.py`.

Test with `make test`.

`arena.c` can be included directly in client code. The members and structs beginning with two underscores `__` should not be referenced in client code.

E.g.,

```C
struct ArenaDir arena;
arena_create(&arena_dir, AT_FDCWD, "log", 4096);

char* arena_path0 = arena_strndup(arena, path0, PATH_MAX + 1);
char* arena_path1 = arena_strndup(arena, path1, PATH_MAX + 1);
struct LogMoveRecord* record = arena_calloc(arena, 1, sizeof(struct LogRecord));
record->path0 = arena_path0;
record->path1 = arena_path1;

// Remove unnecessary mmap segments to reduce virt mem utilization
// arena_path0, arena_path1, and record will no longer be dereferenceable.
// However, new allocations can still be made.
arena_uninstantiate_all_but_last(arena);

// We don't have to worry about running out of memory in the arena (last one was 4096 bytes);
// The arena_dir will allocate a new file with enough size to accomodate the allocation.
arena_calloc(arena, 8192, sizeof(char));
```

After executing this program,

```bash
$ ./parse_arena.py log
(shows memory buffer with path0, null byte, path1, null byte, and record)
```
