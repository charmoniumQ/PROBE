#pragma once

#define _GNU_SOURCE

#include <stdbool.h>
#include <unistd.h>

struct ArenaDir;

/*
 * For each member of global state $X of type $T, we have
 *
 *     const $T __$X_initial = invalid_value_sentinel;
 *     $T __$X = __$X_initial;
 *     static void init_$X();
 *     static $T get_$X();
 *     static $T get_$X_safe();
 *
 * __$X_initial should be an invalid value (or at least very rare value) of $X.
 *
 * Most client code should assume $X has already been initialized, and call get_$X().
 *
 * However, in some instances (so far only used in debug logging), we may need to access before they would have been bootstrapped.
 * In such case, client code should call get_$X_safe(), which will test if $X is initialized, and if not, return a sentinel value
 *
 */

__attribute__((visibility("hidden"))) pid_t get_pid_safe();

__attribute__((visibility("hidden"))) pid_t get_pid();

__attribute__((visibility("hidden"))) extern const char* pid_env_var;

__attribute__((visibility("hidden"))) pid_t get_tid_safe();

__attribute__((visibility("hidden"))) pid_t get_tid();

__attribute__((visibility("hidden"))) bool is_proc_root();

__attribute__((visibility("hidden"))) int get_exec_epoch_safe();

__attribute__((visibility("hidden"))) int get_exec_epoch();

__attribute__((visibility("hidden"))) extern const char* exec_epoch_env_var;

__attribute__((visibility("hidden"))) extern const char* proc_root_env_var;

__attribute__((visibility("hidden"))) bool should_copy_files_eagerly();

__attribute__((visibility("hidden"))) bool should_copy_files_lazily();

__attribute__((visibility("hidden"))) bool should_copy_files();

__attribute__((visibility("hidden"))) struct InodeTable* get_read_inodes();

__attribute__((visibility("hidden"))) struct InodeTable* get_copied_or_overwritten_inodes();

__attribute__((visibility("hidden"))) extern const char* probe_dir_env_var;

__attribute__((visibility("hidden"))) const char* get_probe_dir();

__attribute__((visibility("hidden"))) int get_inodes_dirfd();

__attribute__((visibility("hidden"))) struct ArenaDir* get_op_arena();

__attribute__((visibility("hidden"))) struct ArenaDir* get_data_arena();

__attribute__((visibility("hidden"))) extern const char* get_default_path();

__attribute__((visibility("hidden"))) void ensure_initted();

__attribute__((visibility("hidden"))) void init_after_fork();
