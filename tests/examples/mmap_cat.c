#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/mman.h>

extern char** environ;

int main (int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <file>\n", argv[0]);
        exit(1);
    }
    int fd = open(argv[1], O_RDONLY);
    if (fd == -1) {
        fprintf(stderr, "Could not open %s\n", argv[1]);
        perror("open");
        exit(1);
    }

    struct statx statx_result = { 0 };
    int statx_status = statx(fd, "", AT_EMPTY_PATH, STATX_SIZE, &statx_result);
    if (statx_status != 0) {
        fprintf(stderr, "Could not stat %s\n", argv[1]);
        perror("stat");
        exit(1);
    }

    char* buffer = (char *) mmap(NULL, statx_result.stx_size, PROT_READ, MAP_SHARED, fd, 0);
    if (buffer == NULL || buffer == MAP_FAILED) {
        fprintf(stderr, "Could not mmap fd=%d /* \"%s\" */, size=%lld\n", fd, argv[1], statx_result.stx_size);
        perror("mmap");
        exit(1);
    }

    int close_status = close(fd);
    if (close_status != 0) {
        fprintf(stderr, "Could not close %d %s\n", fd, argv[1]);
        perror("close");
        exit(1);
    }
    ssize_t written = 0;
    while (((size_t) written) < statx_result.stx_size) {
      ssize_t ret = write(STDOUT_FILENO, buffer + written, 10);
        if (ret < 0) {
            fprintf(stderr, "Could not write %p\n", buffer);
            perror("write");
            exit(1);
        }
        written += ret;
    }

    int munmap_ret = munmap(buffer, statx_result.stx_size);
    if (munmap_ret != 0) {
        fprintf(stderr, "Could not munmap\n");
        perror("munmap");
        exit(1);
    }

    return 0;
}
