#include <stdio.h>
#include <sys/stat.h>
#include <fcntl.h>

struct Test {
    int integer;
};

static __thread struct Test test2 = { 42 };

int interpose_creat(const char *pathname, mode_t mode) {
  printf("interposed %d\n", test2.integer);
  printf("pointer %p\n", (void*)&test2);
  test2.integer += 1;
  return 0;
}
static struct __osx_interpose { const void* replacement; const void* replacee; };
static const struct __osx_interpose __osx_interpose_creat __attribute__((used, section("__DATA, __interpose"))) = {(const void* ) (&interpose_creat), (const void* ) (&creat)};
