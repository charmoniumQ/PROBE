#pragma once

#define _GNU_SOURCE

#include "util.h"    // for BORROWED
#include <stdbool.h> // for bool

__attribute__((visibility("hidden"))) bool lookup_on_path(BORROWED const char* bin_name,
                                                          BORROWED char* bin_path)
    __attribute__((nonnull));
