#include "../generated/headers.h"    // for OpData_Tag
#include "../generated/libc_hooks.h" // for client_exit
#include "arena.h"                   // for arena_st...
#include "debug_logging.h"           // for ERROR
#include "global_state.h"            // for get_data...
#include "linux/limits.h"            // for PATH_MAX
#include "prov_buffer.h"             // for get_open...
#include "util.h"                    // for get_real...
#include <fcntl.h>                   // for O_RDONLY
#include <stdbool.h>                 // for false
#include <stdio.h>                   // for NULL
#include <stdlib.h>                  // for free
#include <string.h>                  // for memcpy
#include <sys/types.h>               // for pid_t
#include <unistd.h>                  // for STDOUT_F...

void mark_libs_as_read(int exe_fd, const char* exe) {
#define DIR_LEN 22
    char dir[DIR_LEN] = "/tmp/ld-trace.XXXXXX";
    if (!client_mkdtemp(dir)) {
      ERROR("Could not mkdtemp '%s'", dir);
    }

    char fifo[PATH_MAX];
    memcpy(fifo, dir, DIR_LEN);
    memcpy(fifo + DIR_LEN - 2, "/output.fifo", sizeof("/output.fifo") + 1);
    if (client_mkfifo(fifo, 0600) < 0) {
        client_rmdir(dir);
        ERROR("Could not mkfifo '%s'", fifo);
    }

    pid_t pid = client_fork();
    if (pid < 0) {
        client_unlink(fifo);
        ERROR("Could not fork");
    } else if (pid == 0) {
        int fifo_fd = client_open(fifo, O_WRONLY);
        if (fifo_fd < 0) {
            client_exit(1);
        }
        if (client_dup2(fifo_fd, STDOUT_FILENO) < 0) {
            client_exit(1);
        }
        client_close(fifo_fd);
        char* const argv[] = {(char*)exe, NULL};
        char* const envp[] = {"LD_TRACE_LOADED_OBJECTS=1", NULL};
        client_fexecve(exe_fd, argv, envp);
        client_exit(127);
    }

    /* Read and parse loader output. */
    FILE* stream = client_fopen(fifo, "r");
    if (!stream) {
        client_waitpid(pid, NULL, 0);
        client_unlink(fifo);
        client_rmdir(dir);
        ERROR("Could not fopen fifo");
    }
    char* line = NULL;
    size_t capacity = 0;
    struct ArenaDir* data_arena = get_data_arena_unsafe();
    while (getline(&line, &capacity, stream) >= 0) {
        /*
         * Typical output:
         *   libfoo.so => /absolute/path/libfoo.so (0x...)
         *   /absolute/path/ld-linux.so (0x...)
         *   linux-vdso.so.1 (0x...)
         */

        char* path = line;
        while (path[0] != '/' && path[0] != '\0') {
            ++path;
        }
        if (path[0] == '\0') {
            continue;
        }
        char* end = path + 1;
        while (*end != '\0' && *end != ' ') {
            ++end;
        }
        *end = '\0';
        size_t size = end - path + 1;

        int lib_fd = client_open(path, O_RDONLY);
        if (lib_fd < 0) {
            ERROR("Could not open lib '%s'", path);
        }
        struct Inode inode = get_inode(lib_fd);
        maybe_copy_to_store(READ_ACCESS, lib_fd, inode);
        const char* real_path = get_real_path(lib_fd);
        client_close(lib_fd);

        prov_log_record((struct Op){
            .data =
                {
                    .open_tag = OpData_Open,
                    .open =
                        {
                            .path =
                                {
                                    .directory = get_open_number(AT_FDCWD),
                                    .name = arena_strndup(data_arena, real_path, size),
                                },
#ifdef PROBE_RECORD_REALPATHS
                            .real_path = arena_strndup(data_arena, real_path, PATH_MAX),
#endif
                            .open_number = {0},
                            .inode = inode,
                            .flags = 0,
                            .mode = O_RDONLY,
                            .dir = false,
                            /* This is only used when we _know_ that the file was created, like in pipe() */
                            .creat = false,
                        },
                },
            .ferrno = 0,
        });
    }

    free(line);
    client_fclose(stream);
    client_unlink(fifo);
    client_rmdir(dir);
}
