#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <sys/wait.h>

const char *file = "a.txt";
#define CONTENT_LENGTH 30
const char contents[CONTENT_LENGTH] = "Hello world\n";

int main(__attribute__((unused)) int argc, __attribute__((unused)) char *const argv[]) {
  
    {  
        pid_t pid = fork();
        if (pid < 0) {
            perror("fork");
            return 1;
        } else if (pid == 0) {
            FILE *file_obj = fopen(file, "w");
            if (!file_obj) {
                perror("Opening file");
                return 1;
            }
            if (!fwrite(contents, 1, CONTENT_LENGTH, file_obj)) {
                perror("Writing file");
                return 1;
            }
            if (fclose(file_obj)) {
                perror("Closing file");
                return 1;
            }
            return 0;
        } else {
            int status;
            int ret = waitpid(pid, &status, 0);
            if (ret < 0) {
                perror("waitpid");
            } else if (status != 0) {
                fprintf(stderr, "Child exited %d\n", status);
                return ret;
            }
        }
    }
    
    {
        pid_t pid = fork();
        if (pid < 0) {
            perror("fork");
            return 1;
        } else if (pid == 0) {
            FILE *file_obj = fopen(file, "r");
            if (!file_obj) {
                perror("Opening file");
                return 1;
            }
            char buffer[CONTENT_LENGTH] = {};
            if (!fread(buffer, 1, CONTENT_LENGTH, file_obj)) {
                perror("Reading file");
                return 1;
            }
            fprintf(stdout, "%s", buffer);
            if (fclose(file_obj)) {
                perror("Closing file");
                return 1;
            }
            return 0;
        } else {
            int status;
            int ret = waitpid(pid, &status, 0);
            if (ret < 0) {
                perror("waitpid");
            } else if (status != 0) {
                fprintf(stderr, "Child exited %d\n", status);
                return ret;
            }
        }
    }

    return 0;
}
