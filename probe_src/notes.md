# TODO: handle processes sharing FD table

- `clone()`:
  - If CLONE_FILES is set, the calling process and the child process share the same file descriptor table.
  - If CLONE_FILES is not set, the child process inherits a copy of all file descriptors... Subsequent operations... do not affect the other process.
  - <https://man7.org/linux/man-pages/man2/clone.2.html>

- `unshare()`:
  - CLONE_FILES: Reverse the effect of clone(2) CLONE_FILES flag. Unshare the file descriptor table.

- `close_range()` takes a flag, `CLOSE_RANGE_UNSHARE`: Unshare the specified file descriptors from any other processes before closing them, avoiding races with other threads sharing the same file descriptor table.

- https://www.man7.org/training/download/lusp_fileio_slides-mkerrisk-man7.org.pdf
- https://www.man7.org/training/download/spintro_fileio_slides-mkerrisk-man7.org.pdf
- https://compas.cs.stonybrook.edu/~nhonarmand/courses/fa17/cse306/slides/16-fs_basics.pdf

# TODO: handle cloexec

- `open()/openat()`
  - O_CLOEXEC: Enable the close-on-exec flag.
- `close_range()` also has `CLOSE_RANGE_CLOEXEC`
- `fcntl()` can also change the `CLOEXEC`-ness.

# TODO: intercept low-level stat calls

- https://refspecs.linuxfoundation.org/LSB_1.1.0/gLSB/libcman.html
- https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib---fxstatat-1.html

int stat (const char *__path, struct stat *__statbuf) {
  return __xstat (1, __path, __statbuf);
}

int lstat (const char *__path, struct stat *__statbuf) {
  return __lxstat (1, __path, __statbuf);
}

int fstat (int __fd, struct stat *__statbuf) {
  return __fxstat (1, __fd, __statbuf);
}

int fstatat (int __fd, const char *__filename, struct stat *__statbuf, int __flag) {
  return __fxstatat (1, __fd, __filename, __statbuf, __flag);
}

int mknod (const char *__path, __mode_t __mode, __dev_t __dev) {
  return __xmknod (0, __path, __mode, &__dev);
}

int mknodat (int __fd, const char *__path, __mode_t __mode, __dev_t __dev) {
  return __xmknodat (0, __fd, __path, __mode, &__dev);
}

int stat64 (const char *__path, struct stat64 *__statbuf) {
  return __xstat64 (1, __path, __statbuf);
}

int lstat64 (const char *__path, struct stat64 *__statbuf) {
  return __lxstat64 (1, __path, __statbuf);
}

int fstat64 (int __fd, struct stat64 *__statbuf) {
  return __fxstat64 (1, __fd, __statbuf);
}

int fstatat64 (int __fd, const char *__filename, struct stat64 *__statbuf, int __flag) {
  return __fxstatat64 (1, __fd, __filename, __statbuf, __flag);
}


# TODO: clone: CLONE_FS

- If CLONE_FS is set, the caller and the child process share the same filesystem information. This contains the root of the filesystem, the current working directory, and the umask. Any call to chroot(2), chdir(2), or umask(2) performed by the calling process or the child process also affects the other process.
- If CLONE_FS is not set, the child process works on a copy of the filesystem information of the calling process at the time of the clone call.

# TODO: clone: CLONE_VM

- If A spawns B via clone, data flows from A to B at the time of clone.
- If A spawns B via clone with CLONE_VM, data can flow from A to B or B to A at any time (shared mem).

# A note where to hook process/thread creation/destruction

We need to do something every time a process gets created.
Here are the options:

- On the first operation we intercept, check `is_initialized`. If not, initialize.
- We are already interposing `clone()` and `fork()`; modify the interpose handler to do the initialization.
- Use shared library constructor.

Interposing clone and fork would not work on the very first process, which is not created from an interposed library. E.g., suppose the user types `LD_PRELOAD=libprov.so foobar.exe`; their shell (not instrumented) forks off a process which execs `foobar.exe`.f

Another problem is `vfork()`. The child of `vfork()` isn't allowed to do anything except for `execve()`.

The shared library constructor does not get called after `exec()` (TODO: link), even though the static memory gets wiped after `exec`! This wouldn't work.

Checking on the first operation has the downside that it could slow down every operation a bit (although branch prediction mitigates this), and some processes might not get logged, if they do not do any prov operations before crashing.
What a weird process to have. I'll take this tradeoff any day.

Destruction is different. There is no indication which is the last operation in a given process or thread.

I don't know of a way of hooking a thread's exit. Threads will have to write their information into some structure that can get processed at process-exit time.

One can hook the process's exit with:

- atexit/on_exit()
- Interpose exit()
- library destructor

Not sure which is best.

# TODO: be correct when there are signal handlers

I think this is called re-entrancy.

https://stackoverflow.com/questions/2799023/what-exactly-is-a-reentrant-function

# TODO: default PATH

When PATH is not defined, use /bin and /usr/bin

https://www.man7.org/linux/man-pages/man3/exec.3.html

# TODO: don't zero-initialize, use malloc instead of calloc, or free-then-null  in opt mode

# TODO: Write a wrapper script

- Have --help
  - Link to GitHub repo and issues
- Make sure we are not already tracing prov, or maybe prov tracing should be "stackable"?

# TODO: Make process and thread synchronization

- Note, that by *not* tracking synchronization, PROBE is not precise (might assume dataflow where none exists), but it is still sound (doesn't miss dataflow). Therefore, this is a low priority. It also mostly between threads, which seems unlikely to provide the order between an open-for-read and an open-for-write, in my intuition.
- However, we could implement this as so:
  - Within each thread, maintain a counter on the ops (called op_no, unique within a thread).
  - For mutexes, there is a gloabl map from mutex address to a list of op_no and TID which acquired that mutex.
  - Save the list at program exit
  - Create edges between each pair of adjacent (TID, op_no) in the list.
  - Intercept other synchronization calls and place them behind a mutex. Having a centralized history sounds heavy-handed, so I will prove its necessity by showing one program with two possible happens-before interleavings that both result in indistinguishable distributed histories.
    - For semaphores, suppose we initialize a semaphore with N=0. Suppose we spawn 2 threads that both do [incr, read, decr], except the second thread writes instead of reads. The first thread may happen before the second thread or vice-versa. Both would result in the exact same dynamic trace, therefore we can't infer which happened from the dynamic trace.
    - I think the same can be said for condition variables. For condition variables, we would need to allocate *our own* mutex, and unlock it when the client wants to signal, broadcast, or return from wait, and record the history of (TID, op_no) every time we lock it.
  - Note, that we won't be able to capture synchronization implemented through atomic instructions, and that sounds like it would hit performance too hard anyway. In the mutex case, we are "piggy-backing" our synchronization off of the programs pre-existing synchronization; For condition variables and semaphores, we are trading out a "light" synchronization for a somewhat "heavier" synchronization. Likewise, readers/writers locks have to be "downgraded" to regular locks.
  - https://www.man7.org/linux/man-pages/man3/sem_wait.3.html
  - I think we need to track mmaps, so we can tell when two processes are referring to the same semaphore by different virtual addresses.
  - https://www.man7.org/linux/man-pages/man7/sem_overview.7.html
- https://www.man7.org/linux/man-pages/man3/pthread_cond_init.3.html
- https://www.man7.org/linux/man-pages/man3/pthread_barrier_wait.3p.html
- https://www.man7.org/linux/man-pages/man3/pthread_mutex_lock.3p.html
- https://www.gnu.org/software/libc/manual/html_node/ISO-C-Mutexes.html
- https://www.gnu.org/software/libc/manual/html_node/ISO-C-Condition-Variables.html
