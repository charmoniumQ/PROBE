https://www.man7.org/training/download/lusp_fileio_slides-mkerrisk-man7.org.pdf
https://www.man7.org/training/download/spintro_fileio_slides-mkerrisk-man7.org.pdf
https://compas.cs.stonybrook.edu/~nhonarmand/courses/fa17/cse306/slides/16-fs_basics.pdf

# Stat business

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

