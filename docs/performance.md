Do we need to call stat when `O_TRUNC` is set?

Try reducing the size of the Op structure in libprobe. Can do away with timestamp and thread IDs.

Try only storing the diff of the environment the current process's initial environment in exec.

TODO: arenas and possibly other objects are held by pointer, necessitating 1 extra pointer dereference and sometimes 1 func call. Instead, access them directly (possibly through macros).

Don't even log dups. If we copy the open number, and we never use raw FDs, we don't need to log dups and related fd ops. But we would have to resolve the case where a newly execed process calls write on an inherited filedescriptor. Exec clears out the memory, so we may not easily remember the open-number associated with that FD.

TODO: We have more atomics than necessary. If we assume no races between open and other operations on the same FD, we don't need fd_table to be atomic?

TODO: Delete `call_errno`/`save_errno` handling. If a libc function returns a non-error return, the value of `errno` is undefined, so we don't have to set it. If we return an error, we just have to be sure that we don't call any `client_` functions that may set `errno`.

TODO: Test the performance impact of interpose read/writes.

Delete print_open_fd

Look in to is_rand

Compare syscalls with stat with/without PROBE

Compile with SIMD

Delete device numbers from Inode struct.

Delete arena_sync
