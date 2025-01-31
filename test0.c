#include <stdio.h>
#include <pthread.h> 
#include <fcntl.h>
static __thread int test = 42;
void* thread(void*)
{
    creat("test1.txt", 0644);
    printf("thread1 %d\n", test);
    printf("pointer %p\n", (void*)&test);
    test += 2;
    printf("thread1 %d\n", test);
    return NULL;
}
int main()
{
    creat("test1.txt", 0644);
    pthread_t ptid; 
    pthread_create(&ptid, NULL, &thread, NULL);
    pthread_join(ptid, NULL);
    printf("thread0 %d\n", test);
    printf("pointer %p\n", (void*)&test);
    test -= 2;
    creat("test0.txt", 0644);
    printf("thread0 %d\n", test);
    creat("test1.txt", 0644);
    return 0;
}
