#define _GNU_SOURCE
#include <assert.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <sys/stat.h>
#define ARENA_PERROR
#include "arena.h"
#define DEFAULT_ARENA_SIZE 4096
#define HELLO_WORLD_SIZE 12
#define HELLO_WORLD "hello world"

int main() {
    struct stat stat_buf;
    int stat_ret = fstatat(AT_FDCWD, "arena_data", &stat_buf, 0);
    if (stat_ret != -1 || errno != ENOENT) {
        int ret = system("rm -rf arena_data"); /* OK, just for a test in dev */
        assert(ret == 0);
    }
    errno = 0;
    struct ArenaDir arena_dir;
    int ret = arena_create(&arena_dir, AT_FDCWD, "arena_data", DEFAULT_ARENA_SIZE);
    assert(ret == 0);
    /* This will copy strings into the arena.
     * Eventually, it will overflow the first arena, causing a second to be allocated.
     * */
    for (size_t i = 0; i < DEFAULT_ARENA_SIZE - HELLO_WORLD_SIZE - 1; ++i) {
        char* foo = arena_calloc(&arena_dir, HELLO_WORLD_SIZE, sizeof(char));
        assert(foo);
        strncpy(foo, HELLO_WORLD, HELLO_WORLD_SIZE);
        arena_uninstantiate_all_but_last(&arena_dir);
        arena_uninstantiate_all_but_last(&arena_dir);
    }
    /* This is greater than the old capacity of the arena */
    char* foo = arena_calloc(&arena_dir, 2 * DEFAULT_ARENA_SIZE, sizeof(char));
    assert(foo);
    strncpy(foo, HELLO_WORLD, HELLO_WORLD_SIZE);
    /* This next line is totally optional */
    /* arena_destroy(&arena_dir); */
    return 0;
}
