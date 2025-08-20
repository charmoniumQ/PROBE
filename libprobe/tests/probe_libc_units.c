#define _GNU_SOURCE

#include <criterion/criterion.h>
#define UNIT_TESTS
#include "probe_libc.c"
#define SRC_INCLUDED

#define FUZZING_SEED 69420
#define FUZZING_COUNT 100000

void setup(void) {
    cr_assert(probe_libc_init() == 0, "Failed to initialize probe_libc");
}

Test(init, init) {
    setup();
}

#include "probe_libc_units/test_get_fns.c"
#include "probe_libc_units/test_io_fns.c"
#include "probe_libc_units/test_map_fns.c"
#include "probe_libc_units/test_mem_fns.c"
#include "probe_libc_units/test_str_fns.c"
