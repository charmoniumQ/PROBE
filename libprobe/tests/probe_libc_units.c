#define _GNU_SOURCE

#include <criterion/criterion.h>
#define UNIT_TESTS
#include "probe_libc.c"
#define SRC_INCLUDED
#define FUZZING_SEED 69420

#include "probe_libc_units/test_mem_fns.c"
#include "probe_libc_units/test_getid_fns.c"
#include "probe_libc_units/test_str_fns.c"
