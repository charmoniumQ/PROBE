#ifndef __INTERPOSE_H
#define __INTERPOSE_H

#include <stdint.h>
#include <dlfcn.h>

#if defined(__APPLE__)

/// Structure exposed to the linker for interposition
struct __osx_interpose {
    const void* new_func;
    const void* orig_func;
};

/**
 * Generate a macOS interpose struct
 * Types from: http://opensource.apple.com/source/dyld/dyld-210.2.3/include/mach-o/dyld-interposing.h
 */
#define OSX_INTERPOSE_STRUCT(NEW, OLD) \
    static const struct __osx_interpose __osx_interpose_##OLD \
        __attribute__((used, section("__DATA, __interpose"))) = { \
            (const void*)(uintptr_t)&(NEW), \
            (const void*)(uintptr_t)&(OLD) \
        }

/**
 * Macros to interpose functions on macOS
 */
#define INTERPOSE_C(RETURN_TYPE, NAME, ARG_TYPES, ARGS) \
    static RETURN_TYPE Real__##NAME ARG_TYPES { \
        return NAME ARGS; \
    } \
    RETURN_TYPE __interpose_##NAME ARG_TYPES; \
    OSX_INTERPOSE_STRUCT(__interpose_##NAME, NAME); \
    RETURN_TYPE __interpose_##NAME ARG_TYPES

#else
# error Unsupported platform.
#endif

#endif // __INTERPOSE_H
