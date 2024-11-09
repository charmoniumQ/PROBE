#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h> 
#include <time.h>   
#include <assert.h>

#define NUM_THREADS 3
#define NUM_COUNTERS 3

#ifdef __APPLE__
#include <errno.h>

#ifndef PTHREAD_BARRIER_SERIAL_THREAD
#define PTHREAD_BARRIER_SERIAL_THREAD (-1)
#endif

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int count;
    int tripCount;
} pthread_barrier_t;

typedef int pthread_barrierattr_t;

int pthread_barrier_init(pthread_barrier_t *barrier,
                         const pthread_barrierattr_t *attr,
                         unsigned int count) {
    if (count == 0) {
        return EINVAL;
    }
    int result;
    if ((result = pthread_mutex_init(&barrier->mutex, NULL))) {
        return result;
    }
    if ((result = pthread_cond_init(&barrier->cond, NULL))) {
        pthread_mutex_destroy(&barrier->mutex);
        return result;
    }
    barrier->tripCount = count;
    barrier->count = 0;
    return 0;
}

int pthread_barrier_destroy(pthread_barrier_t *barrier) {
    int result;
    if ((result = pthread_mutex_destroy(&barrier->mutex))) {
        return result;
    }
    if ((result = pthread_cond_destroy(&barrier->cond))) {
        return result;
    }
    return 0;
}

int pthread_barrier_wait(pthread_barrier_t *barrier) {
    int result = 0;
    pthread_mutex_lock(&barrier->mutex);

    barrier->count++;
    if (barrier->count >= barrier->tripCount) {
        barrier->count = 0;
        // Wake up all threads waiting for the barrier
        result = pthread_cond_broadcast(&barrier->cond);
        if (result == 0) {
            // Indicate that this thread is the serial thread
            result = PTHREAD_BARRIER_SERIAL_THREAD;
        }
    } else {
        pthread_cond_wait(&barrier->cond, &barrier->mutex);
    }

    pthread_mutex_unlock(&barrier->mutex);
    return result;
}

#endif

typedef struct {
    long thread_id;
    int* shared_counters;
    pthread_mutex_t* mutexes;
    pthread_barrier_t* barrier;
} thread_args_t;

void* increment_counters(void* args) {
    thread_args_t* thread_args = (thread_args_t*) args;
    long tid = thread_args->thread_id;
    int* counters = thread_args->shared_counters;
    pthread_mutex_t* mutexes = thread_args->mutexes;
    pthread_barrier_t* barrier = thread_args->barrier;

    printf("Thread #%ld: starting.\n", tid);

    int sleep_time = rand() % 3 + 1;
    printf("Thread #%ld: sleeping for %d seconds.\n", tid, sleep_time);
    sleep(sleep_time);

    for (int i = 0; i < NUM_COUNTERS; i++) {
        pthread_mutex_lock(&mutexes[i]);
        printf("Thread #%ld: acquired lock for counter %d.\n", tid, i);
        counters[i]++;
        printf("Thread #%ld: incremented counter %d to %d.\n", tid, i, counters[i]);
        pthread_mutex_unlock(&mutexes[i]);
        printf("Thread #%ld: released lock for counter %d.\n", tid, i);
    }

    char filename[20];
    sprintf(filename, "/tmp/%ld.txt", tid);
    FILE* file = fopen(filename, "w");
    if (file != NULL) {
        fprintf(file, "Thread #%ld was here\n", tid);
        fclose(file);
    } else {
        printf("Thread #%ld: failed to write file.\n", tid);
    }

    printf("Thread #%ld: waiting at barrier.\n", tid);
    int barrier_result = pthread_barrier_wait(barrier);
    if (barrier_result == PTHREAD_BARRIER_SERIAL_THREAD) {
        printf("Thread #%ld: is the serial thread after the barrier.\n", tid);
    }
    printf("Thread #%ld: passed the barrier.\n", tid);

    pthread_exit(NULL);
}

int main() {
    pthread_t threads[NUM_THREADS];
    thread_args_t thread_args[NUM_THREADS];
    pthread_mutex_t mutexes[NUM_COUNTERS];
    pthread_barrier_t barrier;
    int shared_counters[NUM_COUNTERS] = {0};
    int rc;
    long t;

    srand((unsigned int)time(NULL));

    for (int i = 0; i < NUM_COUNTERS; i++) {
        pthread_mutex_init(&mutexes[i], NULL);
    }

    pthread_barrier_init(&barrier, NULL, NUM_THREADS);

    for (t = 0; t < NUM_THREADS; t++) {
        printf("In main: creating thread %ld\n", t);
        thread_args[t].thread_id = t;
        thread_args[t].shared_counters = shared_counters;
        thread_args[t].mutexes = mutexes;
        thread_args[t].barrier = &barrier;

        rc = pthread_create(&threads[t], NULL, increment_counters, (void*)&thread_args[t]);
        if (rc) {
            printf("ERROR; return code from pthread_create() is %d\n", rc);
            exit(-1);
        }
    }

    for (t = 0; t < NUM_THREADS; t++) {
        rc = pthread_join(threads[t], NULL);
        if (rc) {
            printf("ERROR; return code from pthread_join() is %d\n", rc);
            exit(-1);
        }
    }

    for (int i = 0; i < NUM_COUNTERS; i++) {
        pthread_mutex_destroy(&mutexes[i]);
    }

    pthread_barrier_destroy(&barrier);

    printf("Main: checking files written by threads:\n");
    for (t = 0; t < NUM_THREADS; t++) {
        char filename[20];
        sprintf(filename, "/tmp/%ld.txt", t);
        FILE* file = fopen(filename, "r");
        if (file != NULL) {
            char buffer[50];
            char* ret = fgets(buffer, sizeof(buffer), file);
            assert(ret);
            printf("File /tmp/%ld.txt content: %s", t, buffer);
            fclose(file);
        } else {
            printf("File /tmp/%ld.txt not found.\n", t);
        }
    }

    printf("Main: program exiting. Final counter values:\n");
    for (int i = 0; i < NUM_COUNTERS; i++) {
        printf("Counter %d: %d\n", i, shared_counters[i]);
    }

    pthread_exit(NULL);
}

