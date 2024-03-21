#if false
set -ex
cd $(dirname $0)
gcc -Wall -Wextra -DFORK=1 -Og exec.c -o forking_exec
gcc -Wall -Wextra -Og exec.c -o raw_exec
exit 0
#endif

#include <libgen.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include <linux/limits.h>

#define EXPECT(cond, expr) ({\
            int ret = expr; \
            if (!(ret cond)) { \
                fprintf(stderr, "failure on line %d: %s: !(%d %s)\nstrerror: %s\n", __LINE__, #expr, ret, #cond, strerror(errno)); \
                abort(); \
            } \
            ret; \
    })

int main(int argc, char** argv) {
    char orig_argv0 [PATH_MAX];
    strncpy(orig_argv0, argv[0], PATH_MAX);
    char* self_dir = dirname(argv[0]);
    char* self_name = realpath(orig_argv0, NULL);
    printf("Switching to %s\n", self_dir);
    printf("Execing %s\n", self_name);
    EXPECT(== 0, chdir(self_dir));
    if (argc == 1) {
        printf("exec.c path=0\n");
        int fd = EXPECT(> 0, open("test.txt", O_RDONLY));
        EXPECT(== 0, close(fd));
        #ifdef FORK
            pid_t pid = EXPECT(>= 0, fork());
            if (pid == 0) {
                EXPECT(== 0, execlp(self_name, self_name, "1", NULL));
            } else {
                wait(NULL);
            }
        #else
            EXPECT(== 0, execlp(self_name, self_name, "1", NULL));
        #endif
    } else {
        int fd = EXPECT(> 0, open("test2.txt", O_RDONLY));
        EXPECT(== 0, close(fd));
        printf("exec.c path=1\n");
    }
    return 0;
}
