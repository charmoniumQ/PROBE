/*
**
**     which gcc # ensure this is /nix/store/...-gcc
**
**     gcc -Wall -pthread -o test0 test0.c
**
**     gcc -Wall -pthread -fPIC -dynamiclib -o test1.dylib test1.c
**
**     env DYLD_INSERT_LIBRARIES=$PWD/test1.dylib ./test0
**
**     gcc -Wall -pthread -o test2 test2.c
**
**     env DYLD_INSERT_LIBRARIES=$PWD/test1.dylib ./test0
**
*/

#include <stdio.h>
#include <pthread.h> 
#include <fcntl.h>

struct Test {
    int integer;
};

static __thread struct Test test = { 42 };
void* thread(void*)
{
    creat("test1.txt", 0644);
    printf("thread1 %d\n", test.integer);
    printf("pointer %p\n", (void*)&test);
    test.integer += 2;
    printf("thread1 %d\n", test.integer);
    return NULL;
}
int main()
{
    creat("test1.txt", 0644);
    pthread_t ptid; 
    pthread_create(&ptid, NULL, &thread, NULL);
    pthread_join(ptid, NULL);
    printf("thread0 %d\n", test.integer);
    printf("pointer %p\n", (void*)&test);
    test.integer -= 2;
    creat("test0.txt", 0644);
    printf("thread0 %d\n", test.integer);
    creat("test1.txt", 0644);
    return 0;
}
