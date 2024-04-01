#include <iostream>
#include <stdio.h>
#include <pthread.h>
#include <string.h>

template <typename T>
void *threadfunction(void *arg) {
    std::cout << "Hello, World!\n";
    return 0;
}

int main(int argc, char** argv) {
#ifdef USE_THREADS
    pthread_t thread;
    int status = pthread_create(&thread, NULL, threadfunction<int>, NULL);
    if (status) {
        fprintf(stderr, "pthread_create: %s\n", strerror(status));
        return 0;
    }
    pthread_join(thread, NULL);
#else
    threadfunction<int>(NULL);
#endif
    return 0;
}
