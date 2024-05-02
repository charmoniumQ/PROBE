/*
 * This file is responsible for tracking the process-global mapping between
 * file-descriptors and file paths.
 * Since this is process-global, access must be mediate by the readers/writers lock __fd_table_lock.
 * __fd_table is dynamic array of capacity __fd_table_size_factor * i
 * */

const int __fd_table_size_factor =  1024;
static int __fd_table_capacity = 0;
static OWNED struct {
    int dirfd;
    int dirfd_version; /* because the directory indicated by dirfd can change, especially if dirfd == AT_FDCWD! */
    int fd;
    int version;
    OWNED const char* path;
    struct InodeTriple inode_triple;
} * __fd_table = NULL;
static pthread_rwlock_t __fd_table_lock = PTHREAD_RWLOCK_INITIALIZER;

static int __map_fd(int fd) {
    /*
     * I want to be able to store AT_FDCWD in the fd_table, but AT_FDCWD is negative...
     * So I will just shift the FDs over by one (0..N maps to 1..(N+1), with AT_FDCWD mapping to 0).
     * But first, I will rule out -1, which is truly an error value */
    assert(fd != -1);
    return (fd == AT_FDCWD) ? 0 : (fd + 1);
}

static int __unmap_fd(int fd) {
    return (fd == 0) ? AT_FDCWD : (fd - 1);
}

const char* NULL_PATH = "";

static void __fd_table_ensure_capacity(int mapped_fd) {
    if (unlikely(mapped_fd >= __fd_table_capacity)) {
        size_t new_fd_table_capacity = __fd_table_size_factor * (mapped_fd / __fd_table_size_factor + 1);
        /* This allocation is never freed, because it tracks process-global state.
         * It's relatively small, O(max(file descriptor used by tracee))
         *
         * Note that recalloc/realloc(NULL, size) is the same as malloc(size).
         *
         * Note that this has to be zero-initialized, otherwise we won't know which __fd_table entries are populated.
         * */
        EXPECT(, __fd_table = realloc(__fd_table, new_fd_table_capacity * sizeof(*__fd_table)));
        memset(__fd_table + __fd_table_capacity, 0, new_fd_table_capacity - __fd_table_capacity);

        /* Special case going from 0 to n. Must initialize process-global AT_FDCWD */
        if (__fd_table_capacity == 0) {
            /*
             * Initial AT_FDCWD doesn't need a dirfd; it didn't come from anywhere.
             * Usually, the target of an fd is the path relative to the dirfd.
             * However, the very initial AT_FDCWD is simply inherited from the working directory of the parent process.
             *
             * Recording the working directory implies that the execution depends on the value of the working directory, which is not necessarily true.
             * For example, the program `cat ./foo-bar` does not depend on the value of the working directory;
             * Only $(which cat) and ./foo-bar.
             * We can launch that program from any directory containing ./foo-bar provided our system has $(which cat) and the same env.
             * This program is "relocatable".
             * On the other hand, a program like `realpath .` _does_ depend on the value of the working directory.
             * We will only record the working directory in the latter case.
             *
             * Therefore, we set dirfd = 0 and path = "".
             * */
            __fd_table[__map_fd(AT_FDCWD)].dirfd = 0;
            __fd_table[__map_fd(AT_FDCWD)].dirfd_version = 0;
            __fd_table[__map_fd(AT_FDCWD)].fd = AT_FDCWD;
            __fd_table[__map_fd(AT_FDCWD)].version = 0;
            __fd_table[__map_fd(AT_FDCWD)].path = NULL_PATH;
            __fd_table[__map_fd(AT_FDCWD)].inode_triple = get_inode_triple(AT_FDCWD, "");
        }

        __fd_table_capacity = new_fd_table_capacity;
    }
    assert(0 <= mapped_fd && mapped_fd < __fd_table_capacity);
}

/*
 * This is borrowed because the lifetime of normalized path will be bound by the lifetime of Op in the Op buffer
 * But the lifetime of our copy of it is bound by the lifetime of fd_table
 * */
static void fd_table_associate(int fd, int dirfd, BORROWED const char* path, struct InodeTriple inode_triple) {
    if (prov_log_verbose()) {
        fprintf(stderr, "fd_table: %d = openat(%d, \"%s\")\n", fd, dirfd, path);
    }
    fd = __map_fd(fd);
    dirfd = __map_fd(dirfd);
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    __fd_table_ensure_capacity(fd);
    assert(!__fd_table[fd].path);
    /* This allocation is freed by fd_table_close if the tracee properly closes this file or never freed otherwise.
     * The tracee would likely run out of FDs if they didn't close their files. */
    EXPECT(, __fd_table[fd].path = strndup(path, PATH_MAX));
    __fd_table[fd].dirfd = __unmap_fd(dirfd);
    /* Capture dirfd version before doing version++
     * Just in case fd == dirfd, as in chdir("foo") */
    __fd_table[fd].dirfd_version = __fd_table[dirfd].version;
    __fd_table[fd].fd = __unmap_fd(fd);
    __fd_table[fd].inode_triple = inode_triple;
    __fd_table[fd].version++;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

static void fd_table_close(int fd) {
    if (prov_log_verbose()) {
        fprintf(stderr, "fd_table: close(%d /* = openat(%d, \"%s\") */)\n", fd, __fd_table[__map_fd(fd)].dirfd, __fd_table[__map_fd(fd)].path);
    }
    fd = __map_fd(fd);
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    assert(0 <= fd && fd < __fd_table_capacity && __fd_table[fd].path);
    if (__fd_table[fd].path != NULL_PATH) {
        /* NULL_PATH is not dynamically allocated; no need to free. */
        free((char*) __fd_table[fd].path);
    }
    __fd_table[fd].path = NULL;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}

static size_t fd_table_size() {
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    int ret = __fd_table_capacity;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return (ret == 0) ? 0 : __unmap_fd(ret);
}

static bool fd_table_is_used(int fd) {
    fd = __map_fd(fd);
    EXPECT(== 0, pthread_rwlock_rdlock(&__fd_table_lock));
    assert(0 <= fd && fd < __fd_table_capacity && __fd_table[fd].fd == __unmap_fd(fd));
    bool ret = (bool) __fd_table[fd].path;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
    return ret;
}

void fd_table_dup(int oldfd, int newfd) {
    if (prov_log_verbose()) {
        fprintf(stderr, "fd_table: dup2(%d, %d)\n", oldfd, newfd);
    }
    oldfd = __map_fd(oldfd);
    newfd = __map_fd(newfd);
    EXPECT(== 0, pthread_rwlock_wrlock(&__fd_table_lock));
    assert(0 <= oldfd && oldfd < __fd_table_capacity && __fd_table[oldfd].path && __fd_table[oldfd].fd == __unmap_fd(oldfd));
    assert(0 <= newfd && !__fd_table[newfd].path);
    __fd_table_ensure_capacity(newfd);
    /* This allocation is freed by fd_table_close if the tracee properly closes this file or never freed otherwise.
     * The tracee would likely run out of FDs if they didn't close their files. */
    EXPECT(, __fd_table[newfd].path = strndup(__fd_table[oldfd].path, PATH_MAX));
    __fd_table[newfd].dirfd = __fd_table[oldfd].dirfd;
    __fd_table[newfd].dirfd_version = __fd_table[oldfd].dirfd_version;
    __fd_table[newfd].fd = __unmap_fd(newfd);
    __fd_table[newfd].inode_triple = __fd_table[oldfd].inode_triple;
    EXPECT(== 0, pthread_rwlock_unlock(&__fd_table_lock));
}
