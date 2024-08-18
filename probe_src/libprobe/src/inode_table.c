#define INODE_BLOCKS

/*
** Device major and minor are listed here:
** https://www.kernel.org/doc/Documentation/admin-guide/devices.txt
** Assume device major ID is less than 255 for now (should be common case).
** Inodes, on the other hand, are 64 bit integers.
** 256 (major) x 256 (minor) x 2^64 (inodes)
**
** The minimum size is 1 instance of each table.
** The size of a table is length * sizeof(void*).
** sizeof(void*) == 8
** We can split 64 bits into 13 * 4 + 12
** (256 + 256 + 2**13 * 4 + 2**12) * 8 / 1024
** 292 KiB
*/

#define l4_length 4096
long l4_mask = 0x0000000000000FFF;
long l4_shift = 0;
#define l3_length 8192
long l3_mask = 0x0000000001FFF000;
long l3_shift = 64 - 52;
#define l2_length 8192
long l2_mask = 0x0000003FFE000000;
long l2_shift = 64 - 39;
#define l1_length 8192
long l1_mask = 0x0007FFC000000000;
long l1_shift = 64 - 26;
#define l0_length 8192
long l0_mask = 0xFFF8000000000000;
long l0_shift = 64 - 13;

struct InodeL4 {
    bool table[l4_length]; // bits 52 -- 64
};

struct InodeL3 {
    struct InodeL4* table[l3_length]; // bits 39 -- 52
};

struct InodeL2 {
    struct InodeL3* table[l2_length];

    pthread_rwlock_t lock; // bits 26 -- 39
};

struct InodeL1 {
    struct InodeL2* table[l1_length]; // bits 13 -- 26
    pthread_rwlock_t lock;
};

struct InodeL0 {
    struct InodeL1* table[l0_length]; // bits 0 -- 13
    pthread_rwlock_t lock;
};

#define device_minors_length 256
struct DeviceMinorTable {
    struct InodeL0* table[device_minors_length];
    pthread_rwlock_t lock;
};

#define device_majors_length 256
struct DeviceMajorTable {
    struct DeviceMinorTable table[device_majors_length];
    pthread_rwlock_t lock;
};

bool contains(struct DeviceMajorTable* majors, struct Path* path) {
    assert(path->device_major < device_majors_length);
    assert(path->device_minor < device_minors_length);
    struct DeviceMinorTable** minors = &majors->table[path->device_major];
    if (!*minors) {
        *minors = calloc(sizeof(struct DeviceMinorTable));
    }
    struct InodeL0** inode_l0s = &(*minors)->table[path->device_minor];
    if (!*inode_l0s) {
        *inode_l0s = calloc(sizeof(struct InodeL0));
    }
    struct InodeL1** inode_l1s = &(*inode_l0s)->table[(path->inode & l0_mask) >> l0_shift];
    if (!*inode_l1s) {
        *inode_l1s = calloc(sizeof(struct InodeL1));
    }
    struct InodeL2** inode_l2s = &(*inode_l1s)->table[(path->inode & l1_mask) >> l1_shift];
    if (!*inode_l2s) {
        *inode_l2s = calloc(sizeof(struct InodeL2));
    }
    struct InodeL3** inode_l3s = &(*inode_l2s)->table[(path->inode & l2_mask) >> l2_shift];
    if (!*inode_l3s) {
        *inode_l3s = calloc(sizeof(struct InodeL3));
    }
    struct InodeL4** inode_l4s = &(*inode_l3s)->table[(path->inode & l3_mask) >> l3_shift];
    if (!*inode_l4s) {
        *inode_l4s = calloc(sizeof(struct InodeL4));
    }
    bool* data = &(*inode_l4s)->table[(path->inode & l4_mask) >> l4_shift];
    return *data;
}

/*
 * If not exist, put and return True
 * Else, return False
 */
bool put_if_not_exists(struct InodeTable* table, struct Path* path) {
    struct DeviceMinorTable** minors = &majors->table[path->device_major];
    if (!*minors) {
        *minors = calloc(sizeof(struct DeviceMinorTable));
    }
    struct InodeL0** inode_l0s = &(*minors)->table[path->device_minor];
    if (!*inode_l0s) {
        *inode_l0s = calloc(sizeof(struct InodeL0));
    }
    struct InodeL1** inode_l1s = &(*inode_l0s)->table[(path->inode & l0_mask) >> l0_shift];
    if (!*inode_l1s) {
        *inode_l1s = calloc(sizeof(struct InodeL1));
    }
    struct InodeL2** inode_l2s = &(*inode_l1s)->table[(path->inode & l1_mask) >> l1_shift];
    if (!*inode_l2s) {
        *inode_l2s = calloc(sizeof(struct InodeL2));
    }
    struct InodeL3** inode_l3s = &(*inode_l2s)->table[(path->inode & l2_mask) >> l2_shift];
    if (!*inode_l3s) {
        *inode_l3s = calloc(sizeof(struct InodeL3));
    }
    struct InodeL4** inode_l4s = &(*inode_l3s)->table[(path->inode & l3_mask) >> l3_shift];
    if (!*inode_l4s) {
        *inode_l4s = calloc(sizeof(struct InodeL4));
    }
    bool* data = &(*inode_l4s)->table[(path->inode & l4_mask) >> l4_shift];
    bool ret = *data;
    *data = true;
    return ret;
}
