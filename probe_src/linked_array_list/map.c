struct SynchronizedMap {
    pthread_rwlock_t lock;
    void* elements;
};
int smap_add(struct SynchronizedMap smap) {
    smap.lock
}
