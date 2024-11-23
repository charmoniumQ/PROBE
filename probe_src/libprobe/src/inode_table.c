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

#define INODES4_MASK 0x0000000000000FFF
#define INODES3_MASK 0x0000000001FFF000
#define INODES2_MASK 0x0000003FFE000000
#define INODES1_MASK 0x0007FFC000000000
#define INODES0_MASK 0xFFF8000000000000
#define INODES4_SHIFT 0
#define INODES3_SHIFT (64 - 52)
#define INODES2_SHIFT (64 - 39)
#define INODES1_SHIFT (64 - 26)
#define INODES0_SHIFT (64 - 13)
#define INODES4_LENGTH 4096
#define INODES3_LENGTH 8192
#define INODES2_LENGTH 8192
#define INODES1_LENGTH 8192
#define INODES0_LENGTH 8192

#define DEVICE_MINORS 256
#define DEVICE_MAJORS 256

struct IndexTableEntry {
    size_t value;
    pthread_rwlock_t lock;
};

struct IndexTable {
    size_t length;
    /* Note, we will store x + 1, so that 0 in the datastructure means "unoccupied".
     * It's like hilbert's hotel. */
    /* Note, we will store the elements "in-line".
     * It is as if we wrote `size_t elements[N]`.
     * Only reason I don't write it as an array, is because I don't know N.
     * In C++, this would be a template argument, std::array<size_t, n>, since it is known at compile-time.
     * Rather, it isn't known at _struct-definition time_; some people might want the struct to be N = 1024; others N = 256.
     * I considered writing a macro that defines `struct IndexTable_N`, but then I would also have to define the functions N times, and dispatch to the right one.
     * So, we are stuck writing `*(index_table.elements + i)` to get to the ith element.
     *  */
    struct IndexTableEntry elements;

    /* TODO: Try using lock-free datastructure
     * elements[i] could have 3 states:
     * case 0: Empty
     * case 1: Empty, but someone "locked" or "reserved" this for writing.
     * else  : That's the actual value.
     *
     * get_default proceeds as follows:
     * Atomically compare-and-swap(elements[i], 0, 1)
     * If the swap succeeds, then it was 0, is now 1 ("reserved for writing").
     * We can use the factory to compute a value and atomically write it in.
     * Nobody else should be reading/writing it until we replace the 1 with a greater value.
     * If the swap failed, the value must have non-zero.
     * Do an atomic read, looping until the value is not 1.
     * Once the value is not 1, that must be the true value.
     * */
};

static struct IndexTable* index_table_create(size_t length) {
    assert(length);
    struct IndexTable* ret = EXPECT_NONNULL(calloc(sizeof(struct IndexTable) + (length - 1) * sizeof(struct IndexTableEntry), sizeof(char)));
    for (size_t idx = 0; idx < length; ++idx) {
        assert(pthread_rwlock_init(&(&ret->elements + idx)->lock, NULL) == 0);
    }
    ret->length = length;
    return ret;
}

static size_t index_table_get(struct IndexTable* index_table, size_t idx, size_t default_value) {
    assert(index_table);
    assert(idx < index_table->length);
    struct IndexTableEntry* element = &index_table->elements + idx;
    EXPECT(== 0, pthread_rwlock_rdlock(&element->lock));
    size_t ret = element->value;
    EXPECT(== 0, pthread_rwlock_unlock(&element->lock));
    if (ret) {
        return ret - 1;
    } else {
        return default_value;
    }
}

static size_t index_table_get_default(struct IndexTable* index_table, size_t idx, size_t (*factory)(void*), void* arg) {
    assert(index_table);
    assert(idx < index_table->length);
    struct IndexTableEntry* element = &index_table->elements + idx;

    /* Speculatively assume that the element is already occupied */
    EXPECT(== 0, pthread_rwlock_rdlock(&element->lock));
    size_t ret = element->value;
    EXPECT(== 0, pthread_rwlock_unlock(&element->lock));
    if (ret) {
        return ret - 1;
    }

    /* Speculation failed. Gotta try whole thing again writelock.
     * Yes, we have to retry reading the value; what if someone just put the value in?
     * Yes, we could just get a writelock from the beginning, but that would tax all the get_default calls that _don't_ need to write. */
    EXPECT(== 0, pthread_rwlock_wrlock(&element->lock));
    ret = element->value;
    if (!ret) {
        /* element is _still_ not full, and we have a write-lock
         * Compute and write default value. */
        ret = element->value = (*factory)(arg);
    }
    EXPECT(== 0, pthread_rwlock_unlock(&element->lock));
    return ret - 1;
}

static size_t index_table_put(struct IndexTable* index_table, size_t idx, size_t value) {
    assert(index_table);
    assert(idx < index_table->length);
    struct IndexTableEntry* element = &index_table->elements + idx;

    EXPECT(== 0, pthread_rwlock_wrlock(&element->lock));
    size_t ret = element->value;
    element->value = value + 1;
    EXPECT(== 0, pthread_rwlock_unlock(&element->lock));
    return ret - 1;
}

/*
 * This struct "hides" the implementation from users.
 * They don't know about IndexTable or how it is implemented; just functions beginning with inode_table_*.
 * */
struct InodeTable {
    struct IndexTable* majors;
};

static void inode_table_init(struct InodeTable* inode_table) {
    inode_table->majors = index_table_create(DEVICE_MAJORS);
}

static bool inode_table_contains(struct InodeTable* inode_table, const struct Path* path) {
    struct IndexTable* minors  = (struct IndexTable*) index_table_get(inode_table->majors, path->device_major, 0);
    if (!minors) {
        return false;
    }
    struct IndexTable* inodes0 = (struct IndexTable*) index_table_get(minors, path->device_minor, 0);
    if (!inodes0) {
        return false;
    }
    struct IndexTable* inodes1 = (struct IndexTable*) index_table_get(inodes0, (path->inode & INODES0_MASK) >> INODES0_SHIFT, 0);
    if (!inodes1) {
        return false;
    }
    struct IndexTable* inodes2 = (struct IndexTable*) index_table_get(inodes1, (path->inode & INODES1_MASK) >> INODES1_SHIFT, 0);
    if (!inodes2) {
        return false;
    }
    struct IndexTable* inodes3 = (struct IndexTable*) index_table_get(inodes2, (path->inode & INODES2_MASK) >> INODES2_SHIFT, 0);
    if (!inodes3) {
        return false;
    }
    struct IndexTable* inodes4 = (struct IndexTable*) index_table_get(inodes3, (path->inode & INODES3_MASK) >> INODES3_SHIFT, 0);
    if (!inodes4) {
        return false;
    }
    return index_table_get(inodes4, (path->inode & INODES4_MASK) >> INODES4_SHIFT, false);
}

static size_t index_table_factory(void* length_voidp) {
    return (size_t) index_table_create((size_t)length_voidp);
}

/*
 * If not exist, put and return True
 * Else, return False
 */
static bool inode_table_put_if_not_exists(struct InodeTable* inode_table, const struct Path* path) {
    struct IndexTable* minors    = (struct IndexTable*) index_table_get_default(inode_table->majors, path->device_major                           , &index_table_factory, (void*)DEVICE_MINORS );
    struct IndexTable* inodes0   = (struct IndexTable*) index_table_get_default(minors             , path->device_minor                           , &index_table_factory, (void*)INODES0_LENGTH);
    struct IndexTable* inodes1   = (struct IndexTable*) index_table_get_default(inodes0            , (path->inode & INODES0_MASK) >> INODES0_SHIFT, &index_table_factory, (void*)INODES1_LENGTH);
    struct IndexTable* inodes2   = (struct IndexTable*) index_table_get_default(inodes1            , (path->inode & INODES1_MASK) >> INODES1_SHIFT, &index_table_factory, (void*)INODES2_LENGTH);
    struct IndexTable* inodes3   = (struct IndexTable*) index_table_get_default(inodes2            , (path->inode & INODES2_MASK) >> INODES2_SHIFT, &index_table_factory, (void*)INODES3_LENGTH);
    struct IndexTable* inodes4   = (struct IndexTable*) index_table_get_default(inodes3            , (path->inode & INODES3_MASK) >> INODES3_SHIFT, &index_table_factory, (void*)INODES4_LENGTH);
    bool                  exists    = (bool                 ) index_table_put(        inodes4            , (path->inode & INODES4_MASK) >> INODES4_SHIFT, true                                          );
    if (!exists) {
        DEBUG("Put %p %s %d %d %llu", inode_table, path->path, path->device_major, path->device_minor, (unsigned long long)path->inode);
    }
    return !exists;
}
