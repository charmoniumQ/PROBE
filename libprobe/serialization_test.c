#define _GNU_SOURCE
#include <fcntl.h>
#include <linux/limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "generated/headers.h"
#include "src/arena.h"
#include "src/debug_logging.h"

int main() {
    const size_t arena_capacity = 1024;
    EXPECT(== 0, mkdirat(AT_FDCWD, "arenas", 0o777));
    char ops_filename[PATH_MAX] = "arenas/ops/";
    char data_filename[PATH_MAX] = "arenas/data/";
    struct ArenaDir ops_arena;
    struct ArenaDir data_arena;
    arena_create(&ops_arena, ops_filename, strnlen(ops_filename, PATH_MAX), PATH_MAX,
                 arena_capacity);
    arena_create(&data_arena, data_filename, strnlen(data_filename, PATH_MAX), PATH_MAX,
                 arena_capacity);
    struct Inode inode = {
        .device_major = 123,
        .device_minor = 213,
        .inode = 1234567890,
        .mode = 0o0777,
        .mtime =
            {
                .tv_sec = -12345,
                .tv_nsec = 987654321,
            },
        .ctime =
            {
                .tv_sec = -5678,
                .tv_nsec = 123456789,
            },
        .size = 1234,
    };
#define N_OPS 1
    struct Op source[N_OPS] = {
        (struct Op){
            .data = {
                .init_exec_epoch_tag = OpData_InitExecEpoch,
                .init_exec_epoch = {
                    .parent_pid = 1234,
                    .pid = 5678,
                    .epoch = 34,
                    .exe = {
                        .string = {
                            .tag = PathArg_String,
                            .dir_no = {._0 = 0},
                            .name = arena_strndup(&data_arena, "./test.exe", 20),
                        },
                    },
                    .env = arena_copy_argv(&data_arena, (StringArray)environ, 0),
                    .argv = arena_copy_cmdline(&data_arena, (result_sized_mem){
                        .error = 0,
                        .size = 23,
                        .value = "./test.exe\0arg1\0arg2", /* final \0 already included */
                    }),
                    .env = arena_copy_argv(&data_arena, (StringArray)environ, 0),
                    .std_in = inode,
                    .std_out = inode,
                    .std_err = inode,
                },
            },
            .ferrno = 0,
            .pthread_id = 123,
            .iso_c_thread_id = 456,
        },
    };
    struct Op* destination = arena_calloc(&ops_arena, sizeof(struct Op), N_OPS);
    memcpy(destination, source, sizeof(struct Op) * N_OPS);
    arena_destroy(&data_arena);
    arena_destroy(&ops_arena);
}
