#pragma once

#include <stdbool.h>

#define ARENA_USE_UNWRAPPED_LIBC
#define ARENA_PERROR
#include "../arena/include/arena.h"

/*
 * TODO: Do I really need prov_log_disable?
 *
 * Libc functions called from libprobe _won't_ get hooked, so long as we _always_ use the unwrapped functions.
 * Maybe we should grep for that instead?
 */

static _Atomic bool __prov_log_disable = false;
static void prov_log_disable() { __prov_log_disable = true; }
static void prov_log_enable () { __prov_log_disable = false; }
static bool prov_log_is_enabled () { return !__prov_log_disable; }

static void maybe_init_thread();
static void reinit_process();
static void prov_log_disable();
static int get_exec_epoch_safe();
static struct ArenaDir* get_data_arena();

#define ENV_VAR_PREFIX "PROBE_"

#define PRIVATE_ENV_VAR_PREFIX "__PROBE_"
