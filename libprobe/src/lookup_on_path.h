#pragma once

#define _GNU_SOURCE

#include "util.h"

__attribute__((visibility("hidden")))
bool lookup_on_path(BORROWED const char* bin_name, BORROWED char* bin_path);
