void init_function_pointers()
{
  unwrapped_fopen = fopen;
  unwrapped_fclose = fclose;
  unwrapped_openat = openat;
  unwrapped_open = open;
  unwrapped_creat = creat;
  unwrapped_close = close;
  unwrapped_dup = dup;
  unwrapped_dup2 = dup2;
  unwrapped_fcntl = fcntl;
  unwrapped_chdir = chdir;
  unwrapped_fchdir = fchdir;
  unwrapped_opendir = opendir;
  unwrapped_fdopendir = fdopendir;
  unwrapped_readdir = readdir;
  unwrapped_readdir_r = readdir_r;
  unwrapped_closedir = closedir;
  unwrapped_rewinddir = rewinddir;
  unwrapped_telldir = telldir;
  unwrapped_seekdir = seekdir;
  unwrapped_scandir = scandir;
  unwrapped_ftw = ftw;
  unwrapped_nftw = nftw;
  unwrapped_link = link;
  unwrapped_linkat = linkat;
  unwrapped_symlink = symlink;
  unwrapped_symlinkat = symlinkat;
  unwrapped_readlink = readlink;
  unwrapped_readlinkat = readlinkat;
  unwrapped_realpath = realpath;
  unwrapped_unlink = unlink;
  unwrapped_rmdir = rmdir;
  unwrapped_remove = remove;
  unwrapped_rename = rename;
  unwrapped_mkdir = mkdir;
  unwrapped_mkdirat = mkdirat;
  unwrapped_stat = stat;
  unwrapped_fstat = fstat;
  unwrapped_lstat = lstat;
  unwrapped_fstatat = fstatat;
  unwrapped_chown = chown;
  unwrapped_fchown = fchown;
  unwrapped_lchown = lchown;
  unwrapped_fchownat = fchownat;
  unwrapped_chmod = chmod;
  unwrapped_fchmod = fchmod;
  unwrapped_fchmodat = fchmodat;
  unwrapped_access = access;
  unwrapped_faccessat = faccessat;
  unwrapped_utime = utime;
  unwrapped_truncate = truncate;
  unwrapped_truncate64 = truncate64;
  unwrapped_ftruncate = ftruncate;
  unwrapped_ftruncate64 = ftruncate64;
  unwrapped_mknod = mknod;
  unwrapped_tmpfile = tmpfile;
  unwrapped_tmpnam = tmpnam;
  unwrapped_tempnam = tempnam;
  unwrapped_mktemp = mktemp;
  unwrapped_mkstemp = mkstemp;
  unwrapped_mkdtemp = mkdtemp;
  unwrapped_execv = execv;
  unwrapped_execl = execl;
  unwrapped_execve = execve;
  unwrapped_execle = execle;
  unwrapped_execvp = execvp;
  unwrapped_execlp = execlp;
  unwrapped_fork = fork;
  unwrapped_vfork = vfork;
  unwrapped_waitpid = waitpid;
  unwrapped_wait = wait;
  unwrapped_wait4 = wait4;
  unwrapped_wait3 = wait3;
  unwrapped_waitid = waitid;
  unwrapped_pthread_create = pthread_create;
  unwrapped_pthread_join = pthread_join;
}

FILE * interpose_fopen(const char *filename, const char *opentype)
{
  maybe_init_thread();
  struct Op op = {open_op_code, {.open = {.path = create_path_lazy(AT_FDCWD, filename, 0), .flags = fopen_to_flags(opentype), .mode = 0, .fd = -1, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  FILE * ret = unwrapped_fopen(filename, opentype);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret == NULL)
    {
      op.data.open.ferrno = saved_errno;
    }
    else
    {
      op.data.open.fd = fileno(ret);
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fclose(FILE *stream)
{
  maybe_init_thread();
  int fd = fileno(stream);
  struct Op op = {close_op_code, {.close = {fd, fd, 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fclose(stream);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.close.ferrno = (ret == 0) ? (0) : (errno);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_openat(int dirfd, const char *filename, int flags, ...)
{
  maybe_init_thread();
  bool has_mode_arg = ((flags & O_CREAT) != 0) || ((flags & __O_TMPFILE) == __O_TMPFILE);
  struct Op op = {open_op_code, {.open = {.path = create_path_lazy(dirfd, filename, (flags & O_NOFOLLOW) ? (AT_SYMLINK_NOFOLLOW) : (0)), .flags = flags, .mode = 0, .fd = -1, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    if (has_mode_arg)
    {
      va_list ap;
      va_start(ap, flags);
      op.data.open.mode = va_arg(ap, __type_mode_t);
      va_end(ap);
    }
    prov_log_try(op);
  }
  size_t varargs_size = (((sizeof(dirfd)) + (sizeof(filename))) + (sizeof(flags))) + ((has_mode_arg) ? (sizeof(mode_t)) : (0));
  int ret = *((int *) __builtin_apply((void (*)()) unwrapped_openat, __builtin_apply_args(), varargs_size));
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.open.ferrno = (unlikely(ret == (-1))) ? (errno) : (0);
    op.data.open.fd = ret;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_open(const char *filename, int flags, ...)
{
  maybe_init_thread();
  bool has_mode_arg = ((flags & O_CREAT) != 0) || ((flags & __O_TMPFILE) == __O_TMPFILE);
  struct Op op = {open_op_code, {.open = {.path = create_path_lazy(AT_FDCWD, filename, (flags & O_NOFOLLOW) ? (AT_SYMLINK_NOFOLLOW) : (0)), .flags = flags, .mode = 0, .fd = -1, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    if (has_mode_arg)
    {
      va_list ap;
      va_start(ap, flags);
      op.data.open.mode = va_arg(ap, __type_mode_t);
      va_end(ap);
    }
    prov_log_try(op);
  }
  size_t varargs_size = ((sizeof(filename)) + (sizeof(flags))) + ((has_mode_arg) ? (sizeof(mode_t)) : (0));
  int ret = *((int *) __builtin_apply((void (*)()) unwrapped_open, __builtin_apply_args(), varargs_size));
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.open.ferrno = (unlikely(ret == (-1))) ? (errno) : (0);
    op.data.open.fd = ret;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_creat(const char *filename, mode_t mode)
{
  maybe_init_thread();
  struct Op op = {open_op_code, {.open = {.path = create_path_lazy(AT_FDCWD, filename, 0), .flags = (O_WRONLY | O_CREAT) | O_TRUNC, .mode = mode, .fd = -1, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_creat(filename, mode);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.open.ferrno = (unlikely(ret == (-1))) ? (errno) : (0);
    op.data.open.fd = ret;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_close(int filedes)
{
  maybe_init_thread();
  struct Op op = {close_op_code, {.close = {filedes, filedes, 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_close(filedes);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.close.ferrno = (ret == 0) ? (0) : (errno);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_dup(int old)
{
  maybe_init_thread();
  int ret = unwrapped_dup(old);
  return ret;
}

int interpose_dup2(int old, int new)
{
  maybe_init_thread();
  int ret = unwrapped_dup2(old, new);
  return ret;
}

int interpose_fcntl(int filedes, int command, ...)
{
  maybe_init_thread();
  bool int_arg = (((((((((command == F_DUPFD) || (command == F_DUPFD_CLOEXEC)) || (command == F_SETFD)) || (command == F_SETFL)) || (command == F_SETOWN)) || (command == F_SETSIG)) || (command == F_SETLEASE)) || (command == F_NOTIFY)) || (command == F_SETPIPE_SZ)) || (command == F_ADD_SEALS);
  bool ptr_arg = ((((((((command == F_SETLK) || (command == F_SETLKW)) || (command == F_GETLK)) || (command == F_GETOWN_EX)) || (command == F_SETOWN_EX)) || (command == F_GET_RW_HINT)) || (command == F_SET_RW_HINT)) || (command == F_GET_FILE_RW_HINT)) || (command == F_SET_FILE_RW_HINT);
  assert((!int_arg) || (!ptr_arg));
  size_t varargs_size = ((sizeof(filedes)) + (sizeof(command))) + ((int_arg) ? (sizeof(int)) : ((ptr_arg) ? (sizeof(void *)) : (0)));
  int ret = *((int *) __builtin_apply((void (*)()) unwrapped_fcntl, __builtin_apply_args(), varargs_size));
  return ret;
}

int interpose_chdir(const char *filename)
{
  maybe_init_thread();
  struct Op op = {chdir_op_code, {.chdir = {.path = create_path_lazy(AT_FDCWD, filename, 0), .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_chdir(filename);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.chdir.ferrno = (ret == 0) ? (0) : (errno);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fchdir(int filedes)
{
  maybe_init_thread();
  struct Op op = {chdir_op_code, {.chdir = {.path = create_path_lazy(filedes, "", AT_EMPTY_PATH), .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fchdir(filedes);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.chdir.ferrno = (ret == 0) ? (0) : (errno);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

DIR * interpose_opendir(const char *dirname)
{
  maybe_init_thread();
  struct Op op = {open_op_code, {.open = {.path = create_path_lazy(AT_FDCWD, dirname, 0), .flags = (O_RDONLY | O_DIRECTORY) | O_CLOEXEC, .mode = 0, .fd = -1, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  DIR * ret = unwrapped_opendir(dirname);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.open.ferrno = (ret == NULL) ? (errno) : (0);
    op.data.open.fd = try_dirfd(ret);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

DIR * interpose_fdopendir(int fd)
{
  maybe_init_thread();
  struct Op op = {open_op_code, {.open = {.path = create_path_lazy(fd, "", AT_EMPTY_PATH), .flags = (O_RDONLY | O_DIRECTORY) | O_CLOEXEC, .mode = 0, .fd = -1, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  DIR * ret = unwrapped_fdopendir(fd);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.open.ferrno = (ret == NULL) ? (errno) : (0);
    op.data.open.fd = try_dirfd(ret);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

struct dirent * interpose_readdir(DIR *dirstream)
{
  maybe_init_thread();
  int fd = try_dirfd(dirstream);
  struct Op op = {readdir_op_code, {.readdir = {.dir = create_path_lazy(fd, "", AT_EMPTY_PATH), .child = NULL, .all_children = false, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  struct dirent * ret = unwrapped_readdir(dirstream);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret == NULL)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    else
    {
      op.data.readdir.child = arena_strndup(get_data_arena(), ret->d_name, sizeof(ret->d_name));
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_readdir_r(DIR *dirstream, struct dirent *entry, struct dirent **result)
{
  maybe_init_thread();
  int fd = try_dirfd(dirstream);
  struct Op op = {readdir_op_code, {.readdir = {.dir = create_path_lazy(fd, "", AT_EMPTY_PATH), .child = NULL, .all_children = false, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_readdir_r(dirstream, entry, result);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if ((*result) == NULL)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    else
    {
      op.data.readdir.child = arena_strndup(get_data_arena(), entry->d_name, sizeof(entry->d_name));
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_closedir(DIR *dirstream)
{
  maybe_init_thread();
  int fd = try_dirfd(dirstream);
  struct Op op = {close_op_code, {.close = {fd, fd, 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_closedir(dirstream);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.close.ferrno = (ret == 0) ? (0) : (errno);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

void interpose_rewinddir(DIR *dirstream)
{
  maybe_init_thread();
  unwrapped_rewinddir(dirstream);
}

long int interpose_telldir(DIR *dirstream)
{
  maybe_init_thread();
  long int ret = unwrapped_telldir(dirstream);
  return ret;
}

void interpose_seekdir(DIR *dirstream, long int pos)
{
  maybe_init_thread();
  unwrapped_seekdir(dirstream, pos);
}

int interpose_scandir(const char *dir, struct dirent ***namelist, int (*selector)(const struct dirent *), int (*cmp)(const struct dirent **, const struct dirent **))
{
  maybe_init_thread();
  struct Op op = {readdir_op_code, {.readdir = {.dir = create_path_lazy(AT_FDCWD, dir, 0), .child = NULL, .all_children = true}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_scandir(dir, namelist, selector, cmp);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_ftw(const char *filename, __ftw_func_t func, int descriptors)
{
  maybe_init_thread();
  struct Op op = {readdir_op_code, {.readdir = {.dir = create_path_lazy(AT_FDCWD, filename, 0), .child = NULL, .all_children = true}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_ftw(filename, func, descriptors);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_nftw(const char *filename, __nftw_func_t func, int descriptors, int flag)
{
  maybe_init_thread();
  struct Op op = {readdir_op_code, {.readdir = {.dir = create_path_lazy(AT_FDCWD, filename, 0), .child = NULL, .all_children = true}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_nftw(filename, func, descriptors, flag);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_link(const char *oldname, const char *newname)
{
  maybe_init_thread();
  int ret = unwrapped_link(oldname, newname);
  return ret;
}

int interpose_linkat(int oldfd, const char *oldname, int newfd, const char *newname, int flags)
{
  maybe_init_thread();
  int ret = unwrapped_linkat(oldfd, oldname, newfd, newname, flags);
  return ret;
}

int interpose_symlink(const char *oldname, const char *newname)
{
  maybe_init_thread();
  int ret = unwrapped_symlink(oldname, newname);
  return ret;
}

int interpose_symlinkat(const char *target, int newdirfd, const char *linkpath)
{
  maybe_init_thread();
  int ret = unwrapped_symlinkat(target, newdirfd, linkpath);
  return ret;
}

ssize_t interpose_readlink(const char *filename, char *buffer, size_t size)
{
  maybe_init_thread();
  ssize_t ret = unwrapped_readlink(filename, buffer, size);
  return ret;
}

ssize_t interpose_readlinkat(int dirfd, const char *filename, char *buffer, size_t size)
{
  maybe_init_thread();
  ssize_t ret = unwrapped_readlinkat(dirfd, filename, buffer, size);
  return ret;
}

char * interpose_realpath(const char * restrict name, char * restrict resolved)
{
  maybe_init_thread();
  char * ret = unwrapped_realpath(name, resolved);
  return ret;
}

int interpose_unlink(const char *filename)
{
  maybe_init_thread();
  int ret = unwrapped_unlink(filename);
  return ret;
}

int interpose_rmdir(const char *filename)
{
  maybe_init_thread();
  int ret = unwrapped_rmdir(filename);
  return ret;
}

int interpose_remove(const char *filename)
{
  maybe_init_thread();
  int ret = unwrapped_remove(filename);
  return ret;
}

int interpose_rename(const char *oldname, const char *newname)
{
  maybe_init_thread();
  int ret = unwrapped_rename(oldname, newname);
  return ret;
}

int interpose_mkdir(const char *filename, mode_t mode)
{
  maybe_init_thread();
  int ret = unwrapped_mkdir(filename, mode);
  return ret;
}

int interpose_mkdirat(int dirfd, const char *pathname, mode_t mode)
{
  maybe_init_thread();
  int ret = unwrapped_mkdirat(dirfd, pathname, mode);
  return ret;
}

int interpose_stat(const char *filename, struct stat *buf)
{
  maybe_init_thread();
  struct Op op = {stat_op_code, {.stat = {.path = create_path_lazy(AT_FDCWD, filename, 0), .flags = 0, .ferrno = 0, .stat_result = {0}}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_stat(filename, buf);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.stat.ferrno = saved_errno;
    }
    else
    {
      stat_result_from_stat(&op.data.stat.stat_result, buf);
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fstat(int filedes, struct stat *buf)
{
  maybe_init_thread();
  struct Op op = {stat_op_code, {.stat = {.path = create_path_lazy(filedes, "", AT_EMPTY_PATH), .flags = 0, .stat_result = {0}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fstat(filedes, buf);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.stat.ferrno = saved_errno;
    }
    else
    {
      stat_result_from_stat(&op.data.stat.stat_result, buf);
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_lstat(const char *filename, struct stat *buf)
{
  maybe_init_thread();
  struct Op op = {stat_op_code, {.stat = {.path = create_path_lazy(AT_FDCWD, filename, AT_SYMLINK_NOFOLLOW), .flags = AT_SYMLINK_NOFOLLOW, .stat_result = {0}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_lstat(filename, buf);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.stat.ferrno = saved_errno;
    }
    else
    {
      stat_result_from_stat(&op.data.stat.stat_result, buf);
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fstatat(int dirfd, const char * restrict pathname, struct stat * restrict buf, int flags)
{
  maybe_init_thread();
  struct Op op = {stat_op_code, {.stat = {.path = create_path_lazy(dirfd, pathname, flags), .flags = flags, .stat_result = {0}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fstatat(dirfd, pathname, buf, flags);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.stat.ferrno = saved_errno;
    }
    else
    {
      stat_result_from_stat(&op.data.stat.stat_result, buf);
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_chown(const char *filename, uid_t owner, gid_t group)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(AT_FDCWD, filename, 0), .flags = 0, .kind = MetadataOwnership, .value = {.ownership = {.uid = owner, .gid = group}}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_chown(filename, owner, group);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fchown(int filedes, uid_t owner, gid_t group)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(filedes, "", AT_EMPTY_PATH), .flags = AT_EMPTY_PATH, .kind = MetadataOwnership, .value = {.ownership = {.uid = owner, .gid = group}}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fchown(filedes, owner, group);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_lchown(const char *pathname, uid_t owner, gid_t group)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(AT_FDCWD, pathname, AT_SYMLINK_NOFOLLOW), .flags = AT_SYMLINK_NOFOLLOW, .kind = MetadataOwnership, .value = {.ownership = {.uid = owner, .gid = group}}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_lchown(pathname, owner, group);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fchownat(int dirfd, const char *pathname, uid_t owner, gid_t group, int flags)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(dirfd, pathname, flags), .flags = flags, .kind = MetadataOwnership, .value = {.ownership = {.uid = owner, .gid = group}}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fchownat(dirfd, pathname, owner, group, flags);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_chmod(const char *filename, mode_t mode)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(AT_FDCWD, filename, 0), .flags = 0, .kind = MetadataMode, .value = {.mode = mode}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_chmod(filename, mode);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fchmod(int filedes, mode_t mode)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(filedes, "", AT_EMPTY_PATH), .flags = AT_EMPTY_PATH, .kind = MetadataMode, .value = {.mode = mode}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fchmod(filedes, mode);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_fchmodat(int dirfd, const char *pathname, mode_t mode, int flags)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(dirfd, pathname, flags), .flags = flags, .kind = MetadataMode, .value = {.mode = mode}, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_fchmodat(dirfd, pathname, mode, flags);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_access(const char *filename, int how)
{
  maybe_init_thread();
  struct Op op = {access_op_code, {.access = {create_path_lazy(AT_FDCWD, filename, 0), how, 0, 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_access(filename, how);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.access.ferrno = (ret == 0) ? (0) : (errno);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_faccessat(int dirfd, const char *pathname, int mode, int flags)
{
  maybe_init_thread();
  struct Op op = {access_op_code, {.access = {.path = create_path_lazy(dirfd, pathname, 0), .mode = mode, .flags = flags, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_faccessat(dirfd, pathname, mode, flags);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    op.data.access.ferrno = (ret == 0) ? (0) : (errno);
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_utime(const char *filename, const struct utimbuf *times)
{
  maybe_init_thread();
  struct Op op = {update_metadata_op_code, {.update_metadata = {.path = create_path_lazy(AT_FDCWD, filename, 0), .flags = 0, .kind = MetadataTimes, .value = {0}, .ferrno = 0}}, {0}, 0, 0};
  if (times)
  {
    op.data.update_metadata.value.times.is_null = false;
    op.data.update_metadata.value.times.atime.tv_sec = times->actime;
    op.data.update_metadata.value.times.mtime.tv_sec = times->modtime;
  }
  else
  {
    op.data.update_metadata.value.times.is_null = true;
  }
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
  }
  int ret = unwrapped_utime(filename, times);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (ret != 0)
    {
      op.data.readdir.ferrno = saved_errno;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_truncate(const char *filename, off_t length)
{
  maybe_init_thread();
  int ret = unwrapped_truncate(filename, length);
  return ret;
}

int interpose_truncate64(const char *name, off64_t length)
{
  maybe_init_thread();
  int ret = unwrapped_truncate64(name, length);
  return ret;
}

int interpose_ftruncate(int fd, off_t length)
{
  maybe_init_thread();
  int ret = unwrapped_ftruncate(fd, length);
  return ret;
}

int interpose_ftruncate64(int id, off64_t length)
{
  maybe_init_thread();
  int ret = unwrapped_ftruncate64(id, length);
  return ret;
}

int interpose_mknod(const char *filename, mode_t mode, dev_t dev)
{
  maybe_init_thread();
  int ret = unwrapped_mknod(filename, mode, dev);
  return ret;
}

FILE * interpose_tmpfile()
{
  maybe_init_thread();
  FILE * ret = unwrapped_tmpfile();
  return ret;
}

char * interpose_tmpnam(char *result)
{
  maybe_init_thread();
  char * ret = unwrapped_tmpnam(result);
  return ret;
}

char * interpose_tempnam(const char *dir, const char *prefix)
{
  maybe_init_thread();
  char * ret = unwrapped_tempnam(dir, prefix);
  return ret;
}

char * interpose_mktemp(char *template)
{
  maybe_init_thread();
  char * ret = unwrapped_mktemp(template);
  return ret;
}

int interpose_mkstemp(char *template)
{
  maybe_init_thread();
  int ret = unwrapped_mkstemp(template);
  return ret;
}

char * interpose_mkdtemp(char *template)
{
  maybe_init_thread();
  char * ret = unwrapped_mkdtemp(template);
  return ret;
}

int interpose_execv(const char *filename, char * const argv[])
{
  maybe_init_thread();
  size_t argc = 0;
  char * const *copied_argv = arena_copy_argv(get_data_arena(), argv, &argc);
  size_t envc = 0;
  char * const *updated_env = update_env_with_probe_vars(environ, &envc);
  char * const *copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, &envc);
  struct Op op = {exec_op_code, {.exec = {.path = create_path_lazy(0, filename, 0), .ferrno = 0, .argc = argc, .argv = copied_argv, .envc = envc, .env = copied_updated_env}}, {0}, 0, 0};
  op.data.exec.argc = argc;
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  int ret = unwrapped_execvpe(filename, argv, updated_env);
  int saved_errno = errno;
  free((char **) updated_env);
  if (likely(prov_log_is_enabled()))
  {
    assert(errno > 0);
    op.data.exec.ferrno = saved_errno;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_execl(const char *filename, const char *arg0, ...)
{
  maybe_init_thread();
  size_t argc = COUNT_NONNULL_VARARGS(arg0);
  char **argv = malloc((argc + 1) * (sizeof(char *)));
  va_list ap;
  va_start(ap, arg0);
  for (size_t i = 0; i < argc; ++i)
  {
    argv[i] = va_arg(ap, __type_charp);
  }

  va_end(ap);
  argv[argc] = NULL;
  char * const *copied_argv = arena_copy_argv(get_data_arena(), argv, &argc);
  size_t envc = 0;
  char * const *updated_env = update_env_with_probe_vars(environ, &envc);
  char * const *copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, &envc);
  struct Op op = {exec_op_code, {.exec = {.path = create_path_lazy(0, filename, 0), .ferrno = 0, .argc = argc, .argv = copied_argv, .envc = envc, .env = copied_updated_env}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  int ret = unwrapped_execvpe(filename, argv, updated_env);
  int saved_errno = errno;
  free((char **) updated_env);
  free((char **) argv);
  if (likely(prov_log_is_enabled()))
  {
    assert(errno > 0);
    op.data.exec.ferrno = saved_errno;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_execve(const char *filename, char * const argv[], char * const env[])
{
  maybe_init_thread();
  size_t argc = 0;
  char * const *copied_argv = arena_copy_argv(get_data_arena(), argv, &argc);
  size_t envc = 0;
  char * const *updated_env = update_env_with_probe_vars(env, &envc);
  char * const *copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, &envc);
  struct Op op = {exec_op_code, {.exec = {.path = create_path_lazy(0, filename, 0), .ferrno = 0, .argc = argc, .argv = copied_argv, .envc = envc, .env = copied_updated_env}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  int ret = unwrapped_execvpe(filename, argv, updated_env);
  int saved_errno = errno;
  free((char **) updated_env);
  if (likely(prov_log_is_enabled()))
  {
    assert(errno > 0);
    op.data.exec.ferrno = saved_errno;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_execle(const char *filename, const char *arg0, ...)
{
  maybe_init_thread();
  size_t argc = COUNT_NONNULL_VARARGS(arg0) - 1;
  char **argv = malloc((argc + 1) * (sizeof(char *)));
  va_list ap;
  va_start(ap, arg0);
  for (size_t i = 0; i < argc; ++i)
  {
    argv[i] = va_arg(ap, __type_charp);
  }

  argv[argc] = NULL;
  char * const *copied_argv = arena_copy_argv(get_data_arena(), argv, &argc);
  char **env = va_arg(ap, __type_charpp);
  va_end(ap);
  size_t envc = 0;
  char * const *updated_env = update_env_with_probe_vars(env, &envc);
  char * const *copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, &envc);
  struct Op op = {exec_op_code, {.exec = {.path = create_path_lazy(0, filename, 0), .ferrno = 0, .argc = argc, .argv = copied_argv, .envc = envc, .env = copied_updated_env}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  ERROR("Not implemented; I need to figure out how to update the environment.");
  int ret = unwrapped_execvpe(filename, argv, updated_env);
  int saved_errno = errno;
  free((char **) updated_env);
  free((char **) argv);
  if (likely(prov_log_is_enabled()))
  {
    assert(errno > 0);
    op.data.exec.ferrno = saved_errno;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_execvp(const char *filename, char * const argv[])
{
  maybe_init_thread();
  char *bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
  bool found = lookup_on_path(filename, bin_path);
  size_t argc = 0;
  char * const *copied_argv = arena_copy_argv(get_data_arena(), argv, &argc);
  size_t envc = 0;
  char * const *updated_env = update_env_with_probe_vars(environ, &envc);
  char * const *copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, &envc);
  struct Op op = {exec_op_code, {.exec = {.path = (found) ? (create_path_lazy(0, bin_path, 0)) : (null_path), .ferrno = 0, .argc = argc, .argv = copied_argv, .envc = envc, .env = copied_updated_env}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  int ret = unwrapped_execvpe(filename, argv, updated_env);
  int saved_errno = errno;
  free((char **) updated_env);
  if (likely(prov_log_is_enabled()))
  {
    assert(errno > 0);
    op.data.exec.ferrno = saved_errno;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_execlp(const char *filename, const char *arg0, ...)
{
  maybe_init_thread();
  char *bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
  bool found = lookup_on_path(filename, bin_path);
  size_t argc = COUNT_NONNULL_VARARGS(arg0);
  char **argv = malloc((argc + 1) * (sizeof(char *)));
  va_list ap;
  va_start(ap, arg0);
  for (size_t i = 0; i < argc; ++i)
  {
    argv[i] = va_arg(ap, __type_charp);
  }

  argv[argc] = NULL;
  va_end(ap);
  char * const *copied_argv = arena_copy_argv(get_data_arena(), argv, &argc);
  size_t envc = 0;
  char * const *updated_env = update_env_with_probe_vars(environ, &envc);
  char * const *copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, &envc);
  struct Op op = {exec_op_code, {.exec = {.path = (found) ? (create_path_lazy(0, bin_path, 0)) : (null_path), .ferrno = 0, .argc = argc, .argv = copied_argv, .envc = envc, .env = copied_updated_env}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  int ret = unwrapped_execvpe(filename, argv, updated_env);
  int saved_errno = errno;
  free((char **) updated_env);
  free((char **) argv);
  if (likely(prov_log_is_enabled()))
  {
    assert(errno > 0);
    op.data.exec.ferrno = saved_errno;
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

pid_t interpose_fork()
{
  maybe_init_thread();
  struct Op op = {clone_op_code, {.clone = {.flags = 0, .run_pthread_atfork_handlers = true, .task_type = TASK_PID, .task_id = -1, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  pid_t ret = unwrapped_fork();
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (unlikely(ret == (-1)))
    {
      op.data.clone.ferrno = saved_errno;
      prov_log_record(op);
    }
    else
      if (ret == 0)
    {
      reinit_process();
    }
    else
    {
      op.data.clone.task_id = ret;
      prov_log_record(op);
    }
  }
  errno = saved_errno;
  return ret;
}

pid_t interpose_vfork()
{
  maybe_init_thread();
  struct Op op = {clone_op_code, {.clone = {.flags = 0, .run_pthread_atfork_handlers = true, .task_type = TASK_PID, .task_id = 0, .ferrno = 0}}, {0}, 0, 0};
  if (likely(prov_log_is_enabled()))
  {
    prov_log_try(op);
    prov_log_save();
  }
  else
  {
    prov_log_save();
  }
  int ret = unwrapped_fork();
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (unlikely(ret == (-1)))
    {
      op.data.clone.ferrno = saved_errno;
      prov_log_record(op);
    }
    else
      if (ret == 0)
    {
      reinit_process();
    }
    else
    {
      op.data.clone.task_id = ret;
      prov_log_record(op);
    }
  }
  errno = saved_errno;
  return ret;
}

pid_t interpose_waitpid(pid_t pid, int *status_ptr, int options)
{
  maybe_init_thread();
  int status;
  if (status_ptr == NULL)
  {
    status_ptr = &status;
  }
  struct Op op = {wait_op_code, {.wait = {.task_type = TASK_PID, .task_id = 0, .options = options, .status = 0, .ferrno = 0}}, {0}, 0, 0};
  prov_log_try(op);
  pid_t ret = unwrapped_waitpid(pid, status_ptr, options);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (unlikely(ret == (-1)))
    {
      op.data.wait.ferrno = saved_errno;
    }
    else
    {
      op.data.wait.task_id = ret;
      op.data.wait.status = *status_ptr;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

pid_t interpose_wait(int *status_ptr)
{
  maybe_init_thread();
  int status;
  if (status_ptr == NULL)
  {
    status_ptr = &status;
  }
  struct Op op = {wait_op_code, {.wait = {.task_type = TASK_PID, .task_id = -1, .options = 0, .status = 0, .ferrno = 0}}, {0}, 0, 0};
  prov_log_try(op);
  pid_t ret = unwrapped_wait(status_ptr);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (unlikely(ret == (-1)))
    {
      op.data.wait.ferrno = saved_errno;
    }
    else
    {
      op.data.wait.task_id = ret;
      op.data.wait.status = *status_ptr;
    }
    prov_log_record(op);
  }
  errno = saved_errno;
  return ret;
}

pid_t interpose_wait4(pid_t pid, int *status_ptr, int options, struct rusage *usage)
{
  maybe_init_thread();
  struct Op wait_op = {wait_op_code, {.wait = {.task_type = TASK_TID, .task_id = 0, .options = options, .status = 0, .ferrno = 0}}, {0}, 0, 0};
  prov_log_try(wait_op);
  struct Op getrusage_op = {getrusage_op_code, {.getrusage = {.waitpid_arg = pid, .getrusage_arg = 0, .usage = {{0}}, .ferrno = 0}}, {0}, 0, 0};
  if (usage)
  {
    prov_log_try(getrusage_op);
  }
  pid_t ret = unwrapped_wait4(pid, status_ptr, options, usage);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (unlikely(ret == (-1)))
    {
      wait_op.data.wait.ferrno = saved_errno;
      if (usage)
      {
        getrusage_op.data.getrusage.ferrno = saved_errno;
      }
    }
    else
    {
      wait_op.data.wait.task_id = ret;
      wait_op.data.wait.status = *status_ptr;
      if (usage)
      {
        memcpy(&getrusage_op.data.getrusage.usage, usage, sizeof(struct rusage));
      }
    }
    prov_log_record(wait_op);
    if (usage)
    {
      prov_log_record(getrusage_op);
    }
  }
  errno = saved_errno;
  return ret;
}

pid_t interpose_wait3(int *status_ptr, int options, struct rusage *usage)
{
  maybe_init_thread();
  struct Op wait_op = {wait_op_code, {.wait = {.task_type = TASK_PID, .task_id = 0, .options = options, .status = 0, .ferrno = 0}}, {0}, 0, 0};
  prov_log_try(wait_op);
  struct Op getrusage_op = {getrusage_op_code, {.getrusage = {.waitpid_arg = -1, .getrusage_arg = 0, .usage = {{0}}, .ferrno = 0}}, {0}, 0, 0};
  if (usage)
  {
    prov_log_try(getrusage_op);
  }
  pid_t ret = unwrapped_wait3(status_ptr, options, usage);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (unlikely(ret == (-1)))
    {
      wait_op.data.wait.ferrno = saved_errno;
      if (usage)
      {
        getrusage_op.data.getrusage.ferrno = saved_errno;
      }
    }
    else
    {
      wait_op.data.wait.task_id = ret;
      wait_op.data.wait.status = *status_ptr;
      if (usage)
      {
        memcpy(&getrusage_op.data.getrusage.usage, usage, sizeof(struct rusage));
      }
    }
    prov_log_record(wait_op);
    if (usage)
    {
      prov_log_record(getrusage_op);
    }
  }
  errno = saved_errno;
  return ret;
}

int interpose_waitid(idtype_t idtype, id_t id, siginfo_t *infop, int options)
{
  maybe_init_thread();
  struct Op wait_op = {wait_op_code, {.wait = {.task_type = TASK_TID, .task_id = 0, .options = options, .status = 0, .ferrno = 0}}, {0}, 0, 0};
  prov_log_try(wait_op);
  int ret = unwrapped_waitid(idtype, id, infop, options);
  int saved_errno = errno;
  if (likely(prov_log_is_enabled()))
  {
    if (unlikely(ret == (-1)))
    {
      wait_op.data.wait.ferrno = saved_errno;
    }
    else
    {
      wait_op.data.wait.task_id = infop->si_pid;
      wait_op.data.wait.status = infop->si_status;
    }
    prov_log_record(wait_op);
  }
  errno = saved_errno;
  return ret;
}

int interpose_pthread_create(pthread_t * restrict thread, const pthread_attr_t * restrict attr, void *(*start_routine)(void *), void * restrict arg)
{
  maybe_init_thread();
  struct Op op = {clone_op_code, {.clone = {.flags = (((((CLONE_FILES | CLONE_FS) | CLONE_IO) | CLONE_PARENT) | CLONE_SIGHAND) | CLONE_THREAD) | CLONE_VM, .task_type = TASK_PTHREAD, .task_id = 0, .run_pthread_atfork_handlers = false, .ferrno = 0}}, {0}, 0, 0};
  int ret = unwrapped_pthread_create(thread, attr, start_routine, arg);
  int saved_errno = errno;
  if (unlikely(ret != 0))
  {
    if (likely(prov_log_is_enabled()))
    {
      op.data.clone.ferrno = saved_errno;
      prov_log_record(op);
    }
  }
  else
  {
    if (likely(prov_log_is_enabled()))
    {
      op.data.clone.task_id = *thread;
      prov_log_record(op);
    }
  }
  errno = saved_errno;
  return ret;
}

int interpose_pthread_join(pthread_t thread, void **retval)
{
  maybe_init_thread();
  struct Op op = {wait_op_code, {.wait = {.task_type = TASK_PTHREAD, .task_id = thread, .options = 0, .status = 0, .ferrno = 0}}, {0}, 0, 0};
  int ret = unwrapped_pthread_join(thread, retval);
  int saved_errno = errno;
  if (unlikely(ret != 0))
  {
    if (likely(prov_log_is_enabled()))
    {
      op.data.clone.ferrno = saved_errno;
      prov_log_record(op);
    }
  }
  else
  {
    if (likely(prov_log_is_enabled()))
    {
      prov_log_record(op);
    }
  }
  errno = saved_errno;
  return ret;
}

static const struct __osx_interpose __osx_interpose_fopen __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fopen), (const void *) (&fopen)};
static const struct __osx_interpose __osx_interpose_fclose __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fclose), (const void *) (&fclose)};
static const struct __osx_interpose __osx_interpose_openat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_openat), (const void *) (&openat)};
static const struct __osx_interpose __osx_interpose_open __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_open), (const void *) (&open)};
static const struct __osx_interpose __osx_interpose_creat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_creat), (const void *) (&creat)};
static const struct __osx_interpose __osx_interpose_close __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_close), (const void *) (&close)};
static const struct __osx_interpose __osx_interpose_dup __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_dup), (const void *) (&dup)};
static const struct __osx_interpose __osx_interpose_dup2 __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_dup2), (const void *) (&dup2)};
static const struct __osx_interpose __osx_interpose_fcntl __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fcntl), (const void *) (&fcntl)};
static const struct __osx_interpose __osx_interpose_chdir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_chdir), (const void *) (&chdir)};
static const struct __osx_interpose __osx_interpose_fchdir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fchdir), (const void *) (&fchdir)};
static const struct __osx_interpose __osx_interpose_opendir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_opendir), (const void *) (&opendir)};
static const struct __osx_interpose __osx_interpose_fdopendir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fdopendir), (const void *) (&fdopendir)};
static const struct __osx_interpose __osx_interpose_readdir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_readdir), (const void *) (&readdir)};
static const struct __osx_interpose __osx_interpose_readdir_r __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_readdir_r), (const void *) (&readdir_r)};
static const struct __osx_interpose __osx_interpose_closedir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_closedir), (const void *) (&closedir)};
static const struct __osx_interpose __osx_interpose_rewinddir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_rewinddir), (const void *) (&rewinddir)};
static const struct __osx_interpose __osx_interpose_telldir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_telldir), (const void *) (&telldir)};
static const struct __osx_interpose __osx_interpose_seekdir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_seekdir), (const void *) (&seekdir)};
static const struct __osx_interpose __osx_interpose_scandir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_scandir), (const void *) (&scandir)};
static const struct __osx_interpose __osx_interpose_ftw __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_ftw), (const void *) (&ftw)};
static const struct __osx_interpose __osx_interpose_nftw __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_nftw), (const void *) (&nftw)};
static const struct __osx_interpose __osx_interpose_link __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_link), (const void *) (&link)};
static const struct __osx_interpose __osx_interpose_linkat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_linkat), (const void *) (&linkat)};
static const struct __osx_interpose __osx_interpose_symlink __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_symlink), (const void *) (&symlink)};
static const struct __osx_interpose __osx_interpose_symlinkat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_symlinkat), (const void *) (&symlinkat)};
static const struct __osx_interpose __osx_interpose_readlink __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_readlink), (const void *) (&readlink)};
static const struct __osx_interpose __osx_interpose_readlinkat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_readlinkat), (const void *) (&readlinkat)};
static const struct __osx_interpose __osx_interpose_realpath __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_realpath), (const void *) (&realpath)};
static const struct __osx_interpose __osx_interpose_unlink __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_unlink), (const void *) (&unlink)};
static const struct __osx_interpose __osx_interpose_rmdir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_rmdir), (const void *) (&rmdir)};
static const struct __osx_interpose __osx_interpose_remove __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_remove), (const void *) (&remove)};
static const struct __osx_interpose __osx_interpose_rename __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_rename), (const void *) (&rename)};
static const struct __osx_interpose __osx_interpose_mkdir __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_mkdir), (const void *) (&mkdir)};
static const struct __osx_interpose __osx_interpose_mkdirat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_mkdirat), (const void *) (&mkdirat)};
static const struct __osx_interpose __osx_interpose_stat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_stat), (const void *) (&stat)};
static const struct __osx_interpose __osx_interpose_fstat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fstat), (const void *) (&fstat)};
static const struct __osx_interpose __osx_interpose_lstat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_lstat), (const void *) (&lstat)};
static const struct __osx_interpose __osx_interpose_fstatat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fstatat), (const void *) (&fstatat)};
static const struct __osx_interpose __osx_interpose_chown __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_chown), (const void *) (&chown)};
static const struct __osx_interpose __osx_interpose_fchown __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fchown), (const void *) (&fchown)};
static const struct __osx_interpose __osx_interpose_lchown __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_lchown), (const void *) (&lchown)};
static const struct __osx_interpose __osx_interpose_fchownat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fchownat), (const void *) (&fchownat)};
static const struct __osx_interpose __osx_interpose_chmod __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_chmod), (const void *) (&chmod)};
static const struct __osx_interpose __osx_interpose_fchmod __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fchmod), (const void *) (&fchmod)};
static const struct __osx_interpose __osx_interpose_fchmodat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fchmodat), (const void *) (&fchmodat)};
static const struct __osx_interpose __osx_interpose_access __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_access), (const void *) (&access)};
static const struct __osx_interpose __osx_interpose_faccessat __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_faccessat), (const void *) (&faccessat)};
static const struct __osx_interpose __osx_interpose_utime __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_utime), (const void *) (&utime)};
static const struct __osx_interpose __osx_interpose_truncate __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_truncate), (const void *) (&truncate)};
static const struct __osx_interpose __osx_interpose_truncate64 __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_truncate64), (const void *) (&truncate64)};
static const struct __osx_interpose __osx_interpose_ftruncate __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_ftruncate), (const void *) (&ftruncate)};
static const struct __osx_interpose __osx_interpose_ftruncate64 __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_ftruncate64), (const void *) (&ftruncate64)};
static const struct __osx_interpose __osx_interpose_mknod __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_mknod), (const void *) (&mknod)};
static const struct __osx_interpose __osx_interpose_tmpfile __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_tmpfile), (const void *) (&tmpfile)};
static const struct __osx_interpose __osx_interpose_tmpnam __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_tmpnam), (const void *) (&tmpnam)};
static const struct __osx_interpose __osx_interpose_tempnam __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_tempnam), (const void *) (&tempnam)};
static const struct __osx_interpose __osx_interpose_mktemp __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_mktemp), (const void *) (&mktemp)};
static const struct __osx_interpose __osx_interpose_mkstemp __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_mkstemp), (const void *) (&mkstemp)};
static const struct __osx_interpose __osx_interpose_mkdtemp __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_mkdtemp), (const void *) (&mkdtemp)};
static const struct __osx_interpose __osx_interpose_execv __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_execv), (const void *) (&execv)};
static const struct __osx_interpose __osx_interpose_execl __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_execl), (const void *) (&execl)};
static const struct __osx_interpose __osx_interpose_execve __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_execve), (const void *) (&execve)};
static const struct __osx_interpose __osx_interpose_execle __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_execle), (const void *) (&execle)};
static const struct __osx_interpose __osx_interpose_execvp __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_execvp), (const void *) (&execvp)};
static const struct __osx_interpose __osx_interpose_execlp __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_execlp), (const void *) (&execlp)};
static const struct __osx_interpose __osx_interpose_fork __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_fork), (const void *) (&fork)};
static const struct __osx_interpose __osx_interpose_vfork __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_vfork), (const void *) (&vfork)};
static const struct __osx_interpose __osx_interpose_waitpid __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_waitpid), (const void *) (&waitpid)};
static const struct __osx_interpose __osx_interpose_wait __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_wait), (const void *) (&wait)};
static const struct __osx_interpose __osx_interpose_wait4 __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_wait4), (const void *) (&wait4)};
static const struct __osx_interpose __osx_interpose_wait3 __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_wait3), (const void *) (&wait3)};
static const struct __osx_interpose __osx_interpose_waitid __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_waitid), (const void *) (&waitid)};
static const struct __osx_interpose __osx_interpose_pthread_create __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_pthread_create), (const void *) (&pthread_create)};
static const struct __osx_interpose __osx_interpose_pthread_join __attribute__((used, section("__DATA, __interpose"))) = {(const void *) (&interpose_pthread_join), (const void *) (&pthread_join)};
