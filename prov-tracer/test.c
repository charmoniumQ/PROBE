#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <assert.h>

int main() {
    int fd;

    fd = open("test", O_WRONLY | O_CREAT, 0644);
    printf("%ld", write(fd, "Hello world!", 12));
    close(fd);

    fd = open("test", O_WRONLY);
    lseek(fd, 8, SEEK_SET);
    printf("%ld", write(fd, "Hello world!", 12));
    close(fd);

    fd = open("test", O_WRONLY);
    printf("%ld", write(fd, "bye", 3));
    close(fd);

    return 0;
}
