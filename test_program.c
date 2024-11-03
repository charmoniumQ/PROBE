#include <stdio.h>
#include <stdlib.h>

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
    return EXIT_SUCCESS;
}
