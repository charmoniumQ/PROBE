#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>

int main() {
    FILE *file = fopen("flake.nix", "r");
    if (file) {
        int c;
        while ((c = fgetc(file)) != EOF) {
            putchar(c);
        }
        fclose(file);
    } else {
        perror("fopen");
        return EXIT_FAILURE;
    }
    int fd = open("flake.nix", O_RDONLY);
    if (fd != -1) {
        char buffer[100];
        ssize_t bytes = read(fd, buffer, sizeof(buffer)-1);
        if (bytes > 0) {
            buffer[bytes] = '\0';
            printf("Read from open: %s\n", buffer);
        }
        close(fd);
    } else {
        perror("open");
    }
    return EXIT_SUCCESS;
}
