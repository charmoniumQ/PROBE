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

static struct InodeTriple get_inode_triple(int dirfd, BORROWED const char* path) {
    struct InodeTriple ret = {0};
    struct statx statx_buf = {0};
    assert(dirfd > 0 || dirfd == AT_FDCWD);
    assert(path);
    /*
     * AT_EMPTY_PATH means that if path == "", then the target for statx is the dir specified by dirfd.
     * */
    int statx_ret = o_statx(dirfd, path, AT_EMPTY_PATH, STATX_INO, &statx_buf);
    if (statx_ret == 0) {
        ret.device_major = statx_buf.stx_dev_major;
        ret.device_minor = statx_buf.stx_dev_minor;
        ret.inode = statx_buf.stx_ino;
        assert(ret.inode > 0);
    } else {
        ret.inode = -1;
        ret.device_major = -1;
        ret.device_minor = -1;
    }
    if (prov_log_verbose()) {
        fprintf(stderr, "inode_triple: {device_major=%d, device_minor=%d, inode=%d} = get_inode_triple(%d, \"%s\")\n", ret.device_major, ret.device_minor, ret.inode, dirfd, path);
    }
    return ret;
}

static const struct InodeTriple null_inode_triple = {-1, -1, -1};
