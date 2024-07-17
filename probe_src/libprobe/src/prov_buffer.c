static void* buffer_memdup(void** buffer, void* data, size_t length) {
    char* ret = *buffer;
    memcpy(ret, data, string_length);
    *buffer += string_length;
    return ret;
}

static void prov_log_save() {
    /*
     * Before I was using mmap-arena, I needed to explicitly save stuff.
     * I am leaving this here, just in case.
     * */
}

/*
 * Call this to indicate that the process is about to do some op.
 * The values of the op that are not known before executing the call
 * (e.g., fd for open is not known before-hand)
 * just put something random in there.
 * We promise not to read those fields in this function.
 */
static void prov_log_try(struct Op* op) {
    ASSERTF(
        op.op_code != clone_op_code || !(op.data.clone.flags & CLONE_VFORK),
        "We should have replaced clones with vfork with clones without vfork flag set already."
    )
    if (op->pthread_id == 0) {
        op->pthread_id = pthread_self();
    }
    if (op->iso_c_thread_id == 0) {
        op->iso_c_thread_id = thrd_current();
    }
    EXPECT(== 0, clock_gettime(CLOCK_MONOTONIC, &op->time_start));
    if (op->op_code == exec_op_code) {
        prov_log_record(op);
    }
}

/*
 * Call this to indicate that the process did something (successful or not).
 */
static void prov_log_record(struct Op* op) {
#ifdef DEBUG_LOG
        char str[PATH_MAX * 2];
        op_to_human_readable(str, PATH_MAX * 2, op);
        DEBUG("record op: %s", str);
#endif
    arena_uninstantiate_all_but_last(get_op_arena());
}
