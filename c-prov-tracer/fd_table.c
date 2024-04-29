/*
 * This file is responsible for tracking the process-global mapping between
 * file-descriptors and file paths.
 * Since this is process-global, access must be mediate by the readers/writers lock __fd_table_lock.
 * __fd_table is dynamic array of capacity __fd_table_size_factor * i
 * */
const int __fd_table_size_factor =  1024;
static int __fd_table_capacity = 0;
static OWNED const char **__fd_table = NULL;
static pthread_rwlock_t __fd_table_lock = PTHREAD_RWLOCK_INITIALIZER;

static void assert_is_normalized_path(BORROWED const char* path);

/*
 * This is borrowed because the lifetime of normalized path will be bound by the lifetime of Op in the Op buffer
 * But the lifetime of our copy of it is bound by the lifetime of fd_table
 * */
static void fd_table_associate(int fd, BORROWED const char* normalized_path) {
    assert_is_normalized_path(normalized_path);
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
    /* This allocation is freed by fd_table_close if the tracee properly closes this file or never freed otherwise.
     * The tracee would likely run out of FDs if they didn't close their files. */
    EXPECT(, __fd_table[fd] = strdup(normalized_path));
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

static void fd_table_close(int fd) {
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    assert(0 <= fd);
    assert(fd < __fd_table_capacity);
    assert(__fd_table[fd]);
    free((char*) __fd_table[fd]);
    __fd_table[fd] = NULL;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

static size_t fd_table_size() {
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    int ret = __fd_table_capacity;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return ret;
}

static bool fd_table_is_used(int fd) {
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    assert(0 <= fd);
    assert(fd < __fd_table_capacity);
    bool ret = (bool) __fd_table[fd];
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return ret;
}

/*
 * If buf is NULL, return new buffer containing fd path.
 * Otherwise, write fd path into buf. Return buf.
 */
static OWNED char* fd_table_copy(BORROWED char* buf, int fd) {
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    assert(0 <= fd);
    assert(fd < __fd_table_capacity);
    assert_is_normalized_path(__fd_table[fd]);
    if (buf) {
        EXPECT(, strncpy(buf, __fd_table[fd], PATH_MAX));
    } else {
        /* This allocation is freed by the user, since the return is OWNED */
        EXPECT(, buf = strndup( __fd_table[fd], PATH_MAX));
    }
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return buf;
}

static void fd_table_join(BORROWED char* path_buf, int fd, BORROWED const char* rel_path) {
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    assert(0 <= fd);
    assert(fd < __fd_table_capacity);
    assert_is_normalized_path(__fd_table[fd]);
    path_join(path_buf, -1, __fd_table[fd], -1, rel_path);
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

/*
 * An alternative method:
 * */
__attribute__((unused)) static OWNED char* getname(BORROWED const FILE* file) {
    int fd = EXPECT(> 0, fileno((FILE*) file));
    char dev_fd [PATH_MAX + 1] = {0};
    CHECK_SNPRINTF(dev_fd, PATH_MAX, "/dev/fd/%d", fd);
    /* This allocation is freed by user-code, since the returned pointer is OWNED. */
    char* getname_buffer = malloc(PATH_MAX);
    int length = EXPECT(> 0, o_readlink(dev_fd, getname_buffer, PATH_MAX));
    getname_buffer[length] = '\0';
    return getname_buffer;
}
