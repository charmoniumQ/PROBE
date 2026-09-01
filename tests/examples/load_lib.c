#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main(int argc, const char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Must supply 1 arg\n");
        return 1;
    } else {
      const char* path = argv[1];
      void *ret = dlopen(path, 0);
      if (!ret) {
          fprintf(stderr, "Could not dlopen: %s\n%s\n", path, strerror(errno));
          return 2;
      } else {
          return 0;
      }
    }
}
