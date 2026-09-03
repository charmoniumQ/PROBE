#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdbool.h>

//// libprobe/src/debug_logging.h ////
#define LOG(str, ...)                                                                              \
    fprintf(stderr, " %d.%d.%d " __FILE__ ":%d:%s(): " str "\n", 0,    \
            0, 0, __LINE__, __func__, ##__VA_ARGS__)
#define DEBUG(str, ...) LOG("DEBUG " str, ##__VA_ARGS__)

//// libprobe/generated/libc_hooks.h ////
size_t (*client_fread)(void *ptr, size_t size, size_t n, FILE * restrict stream);
size_t (*client_fwrite)(const void *restrict ptr, size_t size, size_t n,
                        FILE *restrict stream);
ssize_t (*client_read)(int fd, void *buf, size_t count);

//// libprobe/src/global_state.c ////
static bool is_process_initted = false;

static void ensure_thread_initted() {
    if (!is_process_initted) {
        fprintf(stderr, "Initializing process\n");
        is_process_initted = true;
        //// libprobe/generated/libc_hooks.c ////
        client_fread = dlsym(RTLD_NEXT, "fread");
        client_fwrite = dlsym(RTLD_NEXT, "fwrite");
        client_read = dlsym(RTLD_NEXT, "read");
    }
}

//// libprobe/generated/libc_hooks.c ////
size_t fread(void *ptr, size_t size, size_t n, FILE * restrict stream)
{
  DEBUG("Interposed fread");
  ensure_thread_initted();
  size_t ret = client_fread(ptr, size, n, stream);
  return ret;
}

size_t fwrite(const void * restrict ptr, size_t size, size_t n, FILE * restrict stream)
{
  DEBUG("Interposed fwrite");
  ensure_thread_initted();
  size_t ret = client_fwrite(ptr, size, n, stream);
  return ret;
}

size_t read(int fd, void* buf, size_t count)
{
  DEBUG("Interposed read");
  ensure_thread_initted();
        Dl_info info;
        if (dladdr(client_read, &info)) {
            DEBUG("dladdr: symbol: %s, library: %s", info.dli_sname, info.dli_fname);
        };
        size_t ret = client_read(fd, buf, count);
  return ret;
}
