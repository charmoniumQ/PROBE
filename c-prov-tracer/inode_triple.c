/*
 * An inode triple uniquely identifies "file contents" on a system.
 *
 * The paths may be different (e.g., ././//../../symlink/bind-mount/foo and ./foo), but if the InodeTriples are element-wise identical, then the two paths refer to the same file.
 */

struct InodeTriple {
    int device_major;
    int device_minor;
    int inode;
};

static const struct InodeTriple null_inode_triple = {-20, -20, -20};

static struct InodeTriple get_inode_triple(int dirfd, BORROWED const char* path) {
    assert(dirfd > 0 || dirfd == AT_FDCWD);
    assert(path);
    int stat_ret;
    struct stat stat_buf;
    /*
     * if path == "", then the target is the dir specified by dirfd.
     * */
    if (path[0] == '\0') {
        stat_ret = o_fstat(dirfd, &stat_buf);
    } else {
        stat_ret = o_fstatat(dirfd, path, &stat_buf, 0);
    }
    if (stat_ret == 0) {
        struct InodeTriple ret = {major(stat_buf.st_dev), minor(stat_buf.st_dev), stat_buf.st_ino};
        assert(ret.inode > 0);
        if (prov_log_verbose()) {
            fprintf(stderr, "inode_triple: {device_major=%d, device_minor=%d, inode=%d} = get_inode_triple(%d, \"%s\")\n", ret.device_major, ret.device_minor, ret.inode, dirfd, path);
        }
        return ret;
    } else {
        if (prov_log_verbose()) {
            fprintf(stderr, "inode_triple: null_inode_triple = get_inode_triple(%d, \"%s\")\n", dirfd, path);
        }
        return null_inode_triple;
    }
}
