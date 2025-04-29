#pragma once

#define _GNU_SOURCE

#include <sys/types.h> // for pid_t

#include "../generated/bindings.h" // for CopyFiles

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

__attribute__((visibility("hidden"))) pid_t get_tid_safe();

__attribute__((visibility("hidden"))) pid_t get_tid();

__attribute__((visibility("hidden"))) const struct FixedPath* get_probe_dir()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) struct FixedPath* get_mut_probe_dir()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) const struct FixedPath* get_libprobe_path()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) enum CopyFiles get_copy_files_mode();

__attribute__((visibility("hidden"))) struct InodeTable* get_read_inodes()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) struct InodeTable* get_copied_or_overwritten_inodes()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) int get_exec_epoch_safe();

__attribute__((visibility("hidden"))) int get_exec_epoch();

__attribute__((visibility("hidden"))) struct ArenaDir* get_op_arena()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) struct ArenaDir* get_data_arena()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) const char* get_default_path()
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) void ensure_thread_initted();

__attribute__((visibility("hidden"))) void init_after_fork();
