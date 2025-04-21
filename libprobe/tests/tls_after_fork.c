#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/wait.h>
#include <pthread.h>

__thread int tls_var = 42;  // Thread-local variable

void* print_var(void* msg) {
    printf("%d.%d: %p=%d %s\n", getpid(), gettid(), &tls_var, tls_var, (char*) msg);
    return NULL;
}

int main() {
    tls_var = 54;
    print_var("Parent pre-fork");
    pthread_t thread;
    assert(pthread_create(&thread, NULL, print_var, "thread") == 0);
    assert(pthread_join(thread, NULL) == 0);
    pid_t pid = fork();
    if (pid == -1) {
        return -1;
    } else if (pid == 0) {
        print_var("Child");
        assert(tls_var == 54);
    } else {
        print_var("Parent post-fork");
        assert(tls_var == 54);
        int status;
        wait(&status);
        assert(status == 0);
    }
    return 0;
}
