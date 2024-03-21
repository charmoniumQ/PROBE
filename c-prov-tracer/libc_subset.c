/* Need these typedefs to make pycparser parse the functions */
typedef void* FILE;
typedef void* DIR;
typedef void* pid_t;
typedef void* mode_t;
typedef void* __ftw_func_t;
typedef void* __ftw64_func_t;
typedef void* __nftw_func_t;
typedef void* __nftw64_func_t;
typedef void* size_t;
typedef void* ssize_t;

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html */
FILE * fopen (const char *filename, const char *opentype);
FILE * fopen64 (const char *filename, const char *opentype);
FILE * freopen (const char *filename, const char *opentype, FILE *stream);
FILE * freopen64 (const char *filename, const char *opentype, FILE *stream);

/* Need: In case an analysis wants to use open-to-close consistency */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html */
int fclose (FILE *stream);
int fcloseall(void);

/* Docs: https://linux.die.net/man/2/openat */
int openat(int dirfd, const char *pathname, int flags, ...);
/* Variadic: See variadic note on open64 */

/* Docs: https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib-openat64.html */
int openat64(int dirfd, const char *pathname, int flags, ...);
/* Variadic: See variadic note on open64
 * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/sysdeps/unix/sysv/linux/openat64.c#L28 */

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html */
int open (const char *filename, int flags, ...);
int open64 (const char *filename, int flags, ...);
/* Variadic:
 * We use the third-arg (of type mode_t) when ((oflag) & O_CREAT) != 0 || ((oflag) & __O_TMPFILE) == __O_TMPFILE.
 * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/sysdeps/unix/sysv/linux/openat.c#L33
 * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/sysdeps/unix/sysv/linux/open.c#L35
 * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/io/fcntl.h#L40 */
int creat (const char *filename, mode_t mode);
int creat64 (const char *filename, mode_t mode);
int close (int filedes);
int close_range (unsigned int lowfd, unsigned int maxfd, int flags);
void closefrom (int lowfd);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Duplicating-Descriptors.html */
int dup (int old);
int dup2 (int old, int new);

/* Docs: https://www.man7.org/linux/man-pages/man2/dup.2.html */
int dup3 (int old, int new);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Control-Operations.html#index-fcntl-function */
int fcntl (int filedes, int command, ...);
/* Variadic:
 * https://www.man7.org/linux/man-pages/man2/fcntl.2.html
 * "The required argument type is indicated in parentheses after each cmd name" */

/* Need: We need this so that opens relative to the current working directory can be resolved */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Working-Directory.html */
int chdir (const char *filename);
int fchdir (int filedes);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-a-Directory.html */
DIR * opendir (const char *dirname);
DIR * fdopendir (int fd);

/*  We don't need to do these, since we track opendir
 * readdir readdir_r readdir64 readdir64_r
 * rewindir, seekdir, telldir
 * scandir, scandirat
 */

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Working-with-Directory-Trees.html */
/* Need: These operations walk a directory recursively */
int ftw (const char *filename, __ftw_func_t func, int descriptors);
int ftw64 (const char *filename, __ftw64_func_t func, int descriptors);
int nftw (const char *filename, __nftw_func_t func, int descriptors, int flag);
int nftw64 (const char *filename, __nftw64_func_t func, int descriptors, int flag);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Hard-Links.html */
int link (const char *oldname, const char *newname);
int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html */
int symlink (const char *oldname, const char *newname);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html */
int symlinkat(const char *target, int newdirfd, const char *linkpath);
ssize_t readlink (const char *filename, char *buffer, size_t size);
ssize_t readlinkat (int dirfd, const char *filename, char *buffer, size_t size);

/* /\* Docs: https://www.gnu.org/software/libc/manual/html_node/Executing-a-File.html *\/ */
/* /\* Need: We need this because exec kills all global variables, o we need to dump our tables before continuing *\/ */
/* int execv (const char *filename, char *const argv[]); */
/* int execl (const char *filename, const char *arg0, ...); */
/* /\* Variadic: var args end with a sentinel NULL arg *\/ */
/* int execve (const char *filename, char *const argv[], char *const env[]); */
/* int fexecve (int fd, char *const argv[], char *const env[]); */
/* int execle (const char *filename, const char *arg0, ...); */
/* /\* Variadic: var args end with a sentinel NULL arg + 1 final char *const env[] *\/ */
/* int execvp (const char *filename, char *const argv[]); */
/* int execlp (const char *filename, const char *arg0, ...); */
/* /\* Variadic: var args end with a sentinel NULL arg *\/ */

/* /\* Docs: https://linux.die.net/man/3/execvpe1 *\/ */
/* int execvpe(const char *file, char *const argv[], char *const envp[]); */

/* Need: Fork does copy-on-write, so we want to deduplicate our structures first */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Creating-a-Process.html */
pid_t fork (void);
pid_t _Fork (void);
pid_t vfork (void);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Process-Completion.html */
pid_t waitpid (pid_t pid, int *status_ptr, int options);
pid_t wait (int *status_ptr);
pid_t wait4 (pid_t pid, int *status_ptr, int options, struct rusage *usage);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/BSD-Wait-Functions.html */
pid_t wait3 (int *status_ptr, int options, struct rusage *usage);
