#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>

extern char** environ;

int main (int argc, char **argv) {
    if (argc != 1 && argc != 2) {
        fprintf(stderr, "Usage: %s [file]\n", argv[0]);
        exit(1);
    }
    int fd;
    if (argc == 1) {
        fd = STDIN_FILENO;
    } else {
        fd = open(argv[1], O_RDONLY);
        if (fd == -1) {
            fprintf(stderr, "Could not open %s\n", argv[1]);
            perror("open");
            exit(1);
        }
    }

    #define BUFFER_SIZE 1024
    char buffer [BUFFER_SIZE];
    size_t size;

    // Pointless dup to test libprobe
    int fd2 = dup(fd);

    while ((size = read(fd2, buffer, BUFFER_SIZE)) > 0) {
        int ret = write(1, buffer, size);
        if (ret < 0) {
            fprintf(stderr, "Could not write\n");
            perror("write");
        }
    }

    close(fd);
    close(fd2);

    return 0;
}
