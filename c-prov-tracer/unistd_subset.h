/*
 * I can't include unistd.h because it also defines dup3.
 */

ssize_t write(int fd, const char* buf, size_t count);

long syscall(long number, ...);

pid_t getpid(void);

struct utimbuf;

char *getcwd(char *buf, size_t size);

#define STDIN_FILENO 0
#define STDOUT_FILENO 1
#define STDERR_FILENO 2
