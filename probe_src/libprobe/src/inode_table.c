#define INODE_BLOCKS

struct InodeTable {
    struct SMap* device_major_map;
};

bool contains(struct InodeTable* table, struct Path* path) {
    struct SMap* device_minor_map = NULL;
    smap_get(table->device_major_map, path->device_major, &device_minor_map);
    if (device_minor_map) {
        struct SMap* inode_map = NULL;
        smap_get(device_minor_map, path->device_minor, &inode_map);
        if (inode_map) {
            void* foo;
            smap_get(inode_map, path->inode, foo);
            return bool(foo);
        }
    }
    return false;
}

/*
 * If not exist, put and return True
 * Else, return False
 */
bool put_if_not_exists(struct InodeTable* table, struct Path* path) {
    struct SMap* device_minor_map;
    smap_get(table->device_major_map, path->device_major, &device_minor_map);
    if (!device_minor_Map) {
        device_minor_map = init_smap();
        smap_put(table->device_major_map, path->device_major, device_minor_map);
    }
    success = smap_get(device_minor_map, path->device_minor, &inode_map);
    if (!success) {
        inode_map = init;
        smap_put(device_inode_map, path->device_minor, inode_map);
    }
    inode_map;
    if (!success) {
        success = smap_get(device_minor_map, device_minor, &inode_map);
        if (success) {
            success = smap_put(inode_map, inode, NULL);
            return success;
        }
    }
    return false;
}
