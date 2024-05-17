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

Exiting will be hooked by interposing `exit`, `_exit`, and maybe signal handlers.

# TODO: be correct when there are signal handlers

I think this is called re-entrancy.
