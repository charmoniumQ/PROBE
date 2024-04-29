/*
 * This library caches the CWD and resolves paths.
 *
 * Note that getcwd() is not necessarily normalized or thread-safe, I think.
 */

static char __cwd [PATH_MAX + 1] = {0};
static size_t __cwd_length = 0;
static pthread_rwlock_t __cwd_lock;

static char * (*o_realpath)(const char * restrict name, char * restrict resolved);
static int (*o_access)(const char *filename, int how);

static void __realpath_getcwd(BORROWED char* dst) {
    char tmp_buf [PATH_MAX + 1] = {0};
    EXPECT(, getcwd(tmp_buf, PATH_MAX + 1));
    EXPECT(, o_realpath(tmp_buf, dst));
}

static void __unlocked_cwd_path_init(bool read_only) {
    /* TODO: it would be safer to use PTHREAD_RWLOCK_INITIALIZER for this lock */
    if (__cwd[0] == '\0') {
        EXPECT(== 0, pthread_rwlock_init(&__cwd_lock, NULL));
        EXPECT(== 0, pthread_rwlock_wrlock(&__cwd_lock));
        __realpath_getcwd(__cwd);
        __cwd_length = strlen(__cwd);
        EXPECT(== 0, pthread_rwlock_unlock(&__cwd_lock));
    }

    if (read_only) {
        EXPECT(== 0, pthread_rwlock_rdlock(&__cwd_lock));
    } else {
        EXPECT(== 0, pthread_rwlock_wrlock(&__cwd_lock));
    }
    /* Postconditions: */
    assert(__cwd);
    assert(strlen(__cwd) == __cwd_length);
    /* Somehow this is recursive: */
    /* assert_is_normalized_path(__cwd); */
    #ifndef NDEBUG
    char expected_cwd[PATH_MAX + 1] = {0};
    __realpath_getcwd(expected_cwd);
    if (strncmp(expected_cwd, __cwd, PATH_MAX)) {
        fprintf(stderr, "realpath(getcwd()) = '%s', but __cwd = '%s'\n", expected_cwd, __cwd);
        abort();
    }
    #endif
}
/*
 * If path_buf is NULL, return new buffer containing cwd.
 * Otherwise, write cwd into path_buf. Return path_buf.
 */
static OWNED char* __cwd_path_copy(BORROWED char* path_buf) {
    __unlocked_cwd_path_init(true);
    if (path_buf) {
        EXPECT(, strncpy(path_buf, __cwd, PATH_MAX));
    } else {
        /* This allocation is freed by the user, since the return is OWNED */
        EXPECT(, path_buf = strndup(__cwd, PATH_MAX));
    }
    EXPECT(== 0, pthread_rwlock_unlock(&__cwd_lock));
    return path_buf;
}

static void __cwd_path_join(char* path_buf, ssize_t rel_path_length, const char* rel_path) {
    __unlocked_cwd_path_init(true);
    path_join(path_buf, __cwd_length, __cwd, rel_path_length, rel_path);
    EXPECT(== 0, pthread_rwlock_unlock(&__cwd_lock));
}

/*
 * If dest is NULL, return new buffer containing normalized path.
 * Otherwise, write normalized_path into dest. Return is dest.
 */
static OWNED char* normalize_path(BORROWED char* dest, int fd, BORROWED const char* path) {
    /* TODO: emit MetadatRead op for symlinks along the path (prefixes of the raw/unresolved path) */
    assert(strlen(path) < PATH_MAX);
    if (path[0] == '/') {
        /* normalize abs path */
        EXPECT(, dest = o_realpath(path, dest));
    } else if (fd == AT_FDCWD) {
        /* normalize path rel to cwd */
        if (path) {
            char abs_path[PATH_MAX + 1] = {0};
            __cwd_path_join(abs_path, -1, path);
            EXPECT(, dest = o_realpath(abs_path, dest));
        } else {
            EXPECT(, dest = __cwd_path_copy(dest));
        }
    } else {
        /* normalize path rel to the dir of fd */
        char abs_path[PATH_MAX + 1] = {0};
        if (path) {
            fd_table_join(abs_path, fd, path);
            EXPECT(, dest = o_realpath(abs_path, dest));
        } else {
            EXPECT(, dest = fd_table_copy(dest, fd));
        }
    }

    /* Postconditions: */
    assert(dest);
    assert(dest[0] == '/');
    return dest;
}

static void assert_is_normalized_path(BORROWED const char* path) {
#ifndef NDEBUG
    if (path[0] != '/') {
        fprintf(stderr, "path does not begin with /: %s\n", path);
        abort();
    }
    char normalized_path [PATH_MAX + 1] = {0};
    normalize_path(normalized_path, AT_FDCWD, path);
    bool cmp = strncmp(path, normalized_path, PATH_MAX);
    if (cmp != 0) {
        fprintf(stderr, "allegedly_normalized_path = '%s', truly_normalized_path = '%s'\n", path, normalized_path);
        abort();
    }
#endif
}

static void track_chdir(BORROWED const char* path) {
    /*
     * Note that calling chdir in two different threads leaves the process in an undetermined directory.
     * Therefore, we usually will not contend for write-access to this resource.
     * That means the performance tax of this lock is relatively low.
     * */
    assert(path);
    assert_is_normalized_path(path);

    __unlocked_cwd_path_init(false);
    EXPECT(, strncpy(__cwd, path, PATH_MAX));
    __cwd_length = strlen(__cwd);
    EXPECT(== 0, pthread_rwlock_unlock(&__cwd_lock));

    /* Postconditions: */
    assert_is_normalized_path(__cwd);
    assert(strlen(__cwd) == __cwd_length);
}

/*
 * If dest is NULL:
 *     If bin_name exists on $PATH: allocate new OWNED buffer containing normalized path of bin_name and return it.
 *     Else: return NULL
 * Else:
 *     If bin_name exists on $PATH: copy bin_name into dest (must be at least PATH_MAX)
 *     Else: return NULL
 * */
static OWNED char* lookup_on_path(BORROWED char* dest, BORROWED const char* bin_name) {
    const char* path_segment_start = getenv("PATH");
    size_t bin_name_length = strlen(bin_name);
    char candidate_path [PATH_MAX + 1] = {0};
    while (path_segment_start[0] != '\0') {
        size_t path_segment_length = strcspn(path_segment_start, ":\0");
        path_join(candidate_path, path_segment_length, path_segment_start, bin_name_length, bin_name);
        if (o_access(candidate_path, X_OK)) {
            /* TODO: bin_name coudl be a symlink. Should emit MetadataRead */
            EXPECT(, dest = realpath(candidate_path, dest));
            /* Postcondition: ret implies is_normalized_path(ret) */
            assert_is_normalized_path(dest);
            return dest;
        }
        path_segment_start = path_segment_start + path_segment_length + 1;
    }
    /* Postcondition: none applicable */
    return NULL;
}
