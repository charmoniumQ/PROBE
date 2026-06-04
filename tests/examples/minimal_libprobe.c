#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdbool.h>
#include <unistd.h>

//// libprobe/src/debug_logging.h ////
#define LOG(str, ...)                                                                              \
    fprintf(stderr, " %d.%d.%d " __FILE__ ":%d:%s(): " str "\n", 0,    \
            0, 0, __LINE__, __func__, ##__VA_ARGS__)
#define DEBUG(str, ...) LOG("DEBUG " str, ##__VA_ARGS__)

//// libprobe/generated/libc_hooks.h ////
size_t (*client_fread)(void *ptr, size_t size, size_t n, FILE * restrict stream);
size_t (*client_fwrite)(const void * restrict ptr, size_t size, size_t n, FILE * restrict stream);

//// libprobe/src/global_state.c ////
static bool is_process_initted = false;

static void ensure_thread_initted() {
    if (!is_process_initted) {
        fprintf(stderr, "%d.%d Initializing process\n", getpid(), getpid());
        is_process_initted = true;
        //// libprobe/generated/libc_hooks.c ////
        client_fread = dlsym(RTLD_NEXT, "client_fread");
        client_fwrite = dlsym(RTLD_NEXT, "client_fwrite");
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
  size_t ret = client_fwrite(ptr, size, n, stream);
  return ret;
}
