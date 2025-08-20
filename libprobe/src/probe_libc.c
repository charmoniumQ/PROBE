#define _GNU_SOURCE

#include "probe_libc.h"

#include <stdio.h>       // for sprintf
#include <sys/syscall.h> // for SYS_exit
#include <unistd.h>      // for syscall

#include "../generated/libc_hooks.h" // for client_exit, client_strerror

// TODO: consider a warning to stderr on failure; needs to be implemented with
// raw syscalls, since calling any fallible code could cause infinite recursion
void exit_with_backup(int status) {
    if (client_exit) {
        client_exit(status);
    }
    syscall(SYS_exit, status);
    __builtin_unreachable();
}

char* strerror_with_backup(int errnum) {
// 9 bytes from the format string, max 20 bytes from stringing a 64-bit
// integer, 1 for null byte, and two for good luck (and alignment)
#define STRERROR_BUFFER 32
    static char backup_strerror_buf[STRERROR_BUFFER];
    if (client_strerror) {
        return client_strerror(errnum);
    }
    snprintf(backup_strerror_buf, STRERROR_BUFFER, "[ERRNO: %d]", errnum);
    return backup_strerror_buf;
}
