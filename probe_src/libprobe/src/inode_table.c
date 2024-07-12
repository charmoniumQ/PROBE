#define INODE_BLOCKS

struct InodeTable {
    struct SynchronizedMap* device_major_map;
};

bool contains(table, struct Path* path) {
    device_minor_map;
    success = smap_get(table->device_major_map, path->device_major, &device_minor_map);
    if (success) {
        inode_map;
        success = smap_get(device_minor_map, path->device_minor, &inode_map);
        if (success) {
            void* foo;
            success = smap_get(inode_map, path->inode, foo);
            return success;
        }
    }
    return false;
}
bool put_if_not_exists(table, struct Path* path) {
    device_minor_map;
    success = smap_get(table->device_major_map, path->device_major, &device_minor_map);
    if (!success) {
        device_minor_map = init;
        smap_put(table->device_major_map, path->device_major, device_minor_map);
    }
    success = smap_get(device_minor_map, path->device_minor, &inode_map);
    if (!success) {
        inode_map = init;
        smap_put(device_inode_map, path->device_minor, inode_map);
    }
    inode_map;
        success = smap_get(device_minor_map, device_minor, &inode_map);
        if (success) {
            success = smap_put(inode_map, inode, NULL);
            return success;
        }
    }
    return false;
}
