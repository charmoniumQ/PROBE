#define EXPECT_ZERO(expr) ({\
            int ret = expr; \
            if (unlikely(ret != 0)) { \
                fprintf(stderr, "failure on line %d: %s\nreturned a non-zero, %d\nstrerror: %s\n", __LINE__, #expr, ret, strerror(errno)); \
                abort(); \
            } \
            ret; \
    })

#define EXPECT_POSITIVE(expr) ({\
            int ret = expr; \
            if (unlikely(ret < 0)) { \
                fprintf(stderr, "failure on line %d: %s\nreturned a negative, %d\nstrerror: %s\n", __LINE__, #expr, ret, strerror(errno)); \
                abort(); \
            } \
            ret; \
    })

int main(int argc, char** argv, char** envp) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <pid_fifo> <signal_fifo> <cmd ...>\n", argv[0]);
        abort();
    }

    char* pid_fifo = argv[1];
    char* signal_fifo = argv[2];
    char* exe = argv[3];
    char** cmd = &argv[3];

    int pid_fd = EXPECT_POSITIVE(open(pid_fifo, O_RDONLY));
    const int pid_strlen_max = 10;
    char pid_str[pid_strlen_max] = {0};
    int pid = getpid()
    int pid_strlen_true = pid_strlen_max - EXPECT_POSITIVE(pid_strlen_max - snprintf_s(pid_str, pid_strlen_max, "%d", pid));
    EXPECT_ZERO(write(pid_fd, pid_str) - pid_strlen_true);
    EXPECT_ZERO(close(pid_fd));

    int signal_fd = EXPECT_POSITIVE(open(signal_fifo, O_RDONLY));
    char buf[1];
    EXPECT_ZERO(read(signal_fd, buf, 1) - 1);
    EXPECT_ZERO(close(signal_fd));

    EXPECT_ZERO(execve(exe, cmd[0], envp));

    // Even if exec fails, we would have aborted by now.
    __builtin_unreachable();
}
