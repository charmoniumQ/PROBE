#include "interpose.h"
#include <stdio.h>
#include <stdarg.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>

// Interpose 'open' function
INTERPOSE_C(int, open, (const char *path, int oflag, ...), (path, oflag)) {
    int result;
    va_list args;
    mode_t mode = 0;

    if (oflag & O_CREAT) {
        va_start(args, oflag);
        mode = va_arg(args, mode_t);
        va_end(args);
        // Log message
        char buffer[256];
        int len = snprintf(buffer, sizeof(buffer),
                           "open called with path: %s, flags: %d, mode: %o\n",
                           path, oflag, mode);
        write(STDERR_FILENO, buffer, len);

        result = Real__open(path, oflag, mode);
    } else {
        char buffer[256];
        int len = snprintf(buffer, sizeof(buffer),
                           "open called with path: %s, flags: %d\n",
                           path, oflag);
        write(STDERR_FILENO, buffer, len);

        result = Real__open(path, oflag);
    }

    return result;
}

// Interpose 'fopen' function
INTERPOSE_C(FILE *, fopen, (const char *filename, const char *mode), (filename, mode)) {
    char buffer[256];
    int len = snprintf(buffer, sizeof(buffer),
                       "fopen called with filename: %s, mode: %s\n",
                       filename, mode);
    write(STDERR_FILENO, buffer, len);

    FILE *result = Real__fopen(filename, mode);
    return result;
}
