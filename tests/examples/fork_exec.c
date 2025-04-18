#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <sys/wait.h>

int main(__attribute__((unused)) int argc, char *const argv[]) {
    fprintf(stderr, "main\n");
    pid_t pid = fork();
    fprintf(stderr, "forked\n");
    if (pid < 0) {
        perror("fork");
        return 1;
    } else if (pid == 0) {
        fprintf(stderr, "child\n");
        execvp(argv[1], &argv[1]);
        // Exec never returns
        // Must be an error in exec
        perror("exec");
        return 1;
    } else {
        fprintf(stderr, "parent\n");
        int status;
        int ret = waitpid(pid, &status, 0);
        if (ret < 0) {
            perror("waitpid");
            return 0;
        } else {
            fprintf(stderr, "Child exited %d\n", status);
            return 0;
        }
    }
}
