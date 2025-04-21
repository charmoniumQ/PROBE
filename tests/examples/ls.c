#define _FILE_OFFSET_BITS 32
#include <stdio.h>
#include <dirent.h>
#include <errno.h>

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <dir>\n", argv[0]);
        return 1;
    }

    DIR *dir = opendir(argv[1]);
    if (!dir) {
        fprintf(stderr, "Error opening dir %s\n", argv[1]);
        perror("opendir");
        return 1;
    }

    struct dirent *entry = readdir(dir);
    while (entry) {
        printf("%s\n", entry->d_name);
        entry = readdir(dir);
    }
    if (errno) {
        fprintf(stderr, "Error while reading from dir %s\n", argv[1]);
        perror("readdir");
        return 1;
    }

    if (closedir(dir)) {
        fprintf(stderr, "Error while closing dir %s\n", argv[1]);
        perror("closedir");
        return 1;
    }

    return 0;
}
