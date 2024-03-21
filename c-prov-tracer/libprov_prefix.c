#define _GNU_SOURCE
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <errno.h>
#include <linux/limits.h>
#include <errno.h>
#include <dlfcn.h>
#include <sys/types.h>
#include <dirent.h>
#include <ftw.h>
#include <sys/resource.h>

/*
 * I can't include unistd.h because it also defines dup3.
 */
pid_t getpid(void);
pid_t gettid(void);

#define EXPECT(cond, expr) ({\
            int ret = expr; \
            if (!(ret cond)) { \
                fprintf(stderr, "failure on line %d: %s: !(%d %s)\nstrerror: %s\n", __LINE__, #expr, ret, #cond, strerror(errno)); \
                abort(); \
            } \
            ret; \
    })

void setup_libprov() __attribute__ ((constructor));

static __thread FILE* log = NULL;

FILE * (*_o_fopen) ( const char * filename, const char * mode );

FILE* get_prov_log_file() {
    if (log == NULL) {
        char log_name [PATH_MAX];
        struct timespec ts;
        EXPECT(== 0, timespec_get(&ts, TIME_UTC));
        EXPECT(> 0, snprintf(
            log_name,
            PATH_MAX,
            "prov.pid-%d.tid-%d.sec-%ld.nsec-%ld",
            getpid(), gettid(), ts.tv_sec, ts.tv_nsec
        ));
        log = _o_fopen(log_name, "a");
        EXPECT(== 0, log == NULL);
        setbuf(log, NULL);
    }
    return log;
}
