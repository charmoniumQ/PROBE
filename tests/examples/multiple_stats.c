#include <stdio.h>
#include <assert.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>

extern char** environ;

int main (int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <repetitions> <file>\n", argv[0]);
        exit(1);
    }
    size_t repetitions = atol(argv[1]);
    const char* fname = argv[2];
    assert(repetitions != 0);

    for (size_t i = 0; i < repetitions; ++i) {
        struct stat buf;
        stat(fname, &buf);
    }

    return 0;
}
