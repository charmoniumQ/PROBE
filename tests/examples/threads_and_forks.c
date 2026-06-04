#include <unistd.h>
#include <stdio.h>
#include <pthread.h>
#include <sys/wait.h>

void* thread_main(void* _) {
    printf("Hello from thread\n");
    return NULL;
}

int main() {
    pthread_t thread;
    int rc = pthread_create(&thread, NULL, thread_main, NULL);
    if (rc != 0) {
        perror("pthread_create");
        return 1;
    }
    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        return 1;
    } else if (pid == 0) {
        printf("Hello from child\n");
    } else {
        int status;
        int ret = waitpid(pid, &status, 0);
        if (ret < 0) {
            perror("waitpid");
            return 1;
        }
    }
    int rc2 = pthread_join(thread, NULL);
    if (rc2 != 0) {
        perror("pthread_join");
        return 1;
    }
    return 0;
}
