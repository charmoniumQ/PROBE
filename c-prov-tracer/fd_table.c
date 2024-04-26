const int __fd_table_size_factor =  1024;
static int __fd_table_capacity = 0;
static int* __fd_table = NULL;
static pthread_rwlock_t __fd_table_lock;
static struct Path* __cwd = NULL;
static pthread_rwlock_t __cwd_lock;

/* TODO: Put a mutex in all of these */

void fd_table_associate(__attribute__((unused)) struct Path path, int fd) {
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    if (__fd_table == NULL) {
        __fd_table = calloc(__fd_table_size_factor, sizeof(int));
        __fd_table_capacity = __fd_table_size_factor;
    }
    if (fd >= __fd_table_capacity) {
        size_t multiples = fd / __fd_table_size_factor;
        __fd_table = calloc(__fd_table_size_factor * (multiples + 1), sizeof(int));
        __fd_table_capacity = __fd_table_size_factor * (multiples + 1);
    }
    assert(fd < __fd_table_capacity);
    __fd_table[fd] = 1;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

void fd_table_close(int fd) {
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    assert(fd < __fd_table_capacity);
    __fd_table[fd] = 0;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

size_t fd_table_size() {
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    int ret = __fd_table_capacity;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return ret;
}

bool fd_table_is_used(int fd) {
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    assert(fd < __fd_table_capacity);
    bool ret = __fd_table[fd];
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return ret;
}

void dir_tracker_chdir(struct Path path) {
    EXPECT(== 0, pthread_rwlock_wrlock(&__cwd_lock));
    if (__cwd != NULL) {
        free((char*)__cwd->raw_path);
        __cwd->raw_path = NULL;
    }
    __cwd->raw_path = strdup(path.raw_path);
    EXPECT(== 0, pthread_rwlock_unlock(&__cwd_lock));
}
