
/*
 * __fd_table is dynamic array of capacity __fd_table_size_factor * i
 * We will lock this with a readers/writers lock.
 * The lock has three states: available, some-people-are-currently-reading, and one-person-is-currently-writing.
 * It permits parallel reads, which mitigates the performance hit of using a lock.
 * */
const int __fd_table_size_factor =  1024;
static int __fd_table_capacity = 0;
static struct Path* __fd_table = NULL;
static pthread_rwlock_t __fd_table_lock;

void fd_table_associate(struct Path path, int fd) {
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    if (fd >= __fd_table_capacity) {
        size_t multiples = fd / __fd_table_size_factor + 1;
        /* This allocation is never freed, because it tracks process-global state.
         * It's relatively small, O(max(file descriptor used by tracee))
         *
         * Note that realloc(NULL, size) is the same as malloc(size).
         * */
        EXPECT(, __fd_table = realloc(__fd_table, __fd_table_size_factor * multiples * sizeof(*__fd_table)));
        __fd_table_capacity = __fd_table_size_factor * multiples;
    }
    assert(0 <= fd);
    assert(fd < __fd_table_capacity);
    /* Assertion: Did Linux kernel use an existing file-descriptor for a new file? Maybe we missed the close(fd). */
    assert(!__fd_table[fd].raw_path);
    /* This allocation is freed by fd_table_close if the tracee properly closes this file or never freed otherwise. Oh well. */
    EXPECT(, __fd_table[fd].raw_path = strdup(path.raw_path));
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

void fd_table_close(int fd) {
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    assert(0 <= fd);
    assert(fd < __fd_table_capacity);
    assert(__fd_table[fd].raw_path);
    free((char*) __fd_table[fd].raw_path);
    __fd_table[fd].raw_path = NULL;
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
    assert(0 <= fd);
    assert(fd < __fd_table_capacity);
    bool ret = (bool) __fd_table[fd].raw_path;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return ret;
}

static struct Path* __cwd = NULL;
static pthread_rwlock_t __cwd_lock;

void dir_tracker_chdir(struct Path path) {
    /*
     * Note that calling chdir in two different threads leaves the process in an undetermined directory.
     * Therefore, we usually will not contend for write-access to this resource.
     * That means the performance tax of this lock is relatively low.
     * */
    EXPECT(== 0, pthread_rwlock_wrlock(&__cwd_lock));
    if (__cwd != NULL) {
        free((char*)__cwd->raw_path);
        __cwd->raw_path = NULL;
    }
    __cwd->raw_path = strdup(path.raw_path);
    EXPECT(== 0, pthread_rwlock_unlock(&__cwd_lock));
}
