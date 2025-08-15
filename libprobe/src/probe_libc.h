#pragma once

#define _GNU_SOURCE

__attribute__((noreturn, visibility("hidden"))) void exit_with_backup(int status);

__attribute__((visibility("hidden"))) char* strerror_with_backup(int errnum);
