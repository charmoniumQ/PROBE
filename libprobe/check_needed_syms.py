import subprocess
import sys

allowed = {
    "bcmp",
    "calloc",
    "__confstr_chk",
    "__cxa_finalize",
    "dirfd",
    "dlsym",
    "__environ",
    "environ",
    "__errno_location",
    "fileno",
    "free",
    "__getcwd_chk",
    "getenv",
    "getpagesize",
    "getpid",
    "getppid",
    "gettid",
    "__gmon_start__",
    "_ITM_deregisterTMCloneTable",
    "_ITM_registerTMCloneTable",
    "malloc",
    "memcpy",
    "__memcpy_chk",
    "memset",
    "msync",
    "pthread_getspecific",
    "pthread_key_create",
    "pthread_rwlock_init",
    "pthread_rwlock_rdlock",
    "pthread_rwlock_unlock",
    "pthread_rwlock_wrlock",
    "pthread_setspecific",
    "read",
    "realloc",
    "__register_atfork",
    "sendfile",
    "__stack_chk_fail",
    "stderr",
    "strcmp",
    "strlen",
    "strncpy",
    "strnlen",
    "syscall",
    "thrd_current",
    "__tls_get_addr",
    "__vfprintf_chk",
    "__vsnprintf_chk",
    "write",
    "strerror",
}

unneeded = allowed

for file in sys.argv[1:]:
    needed =  {
        sym.split("@")[0]
        for sym in subprocess.run(
            ["nm", "--dynamic", "--undefined-only", "--just-symbols", file],
            check=True,
            capture_output=True,
            text=True
        ).stdout.strip().splitlines()
    }

    diff = needed - allowed
    if diff:
        print(f"(Needed) ERROR: '{file}' had unallowed needed symbols: {diff}")
        sys.exit(1)

    reverse_diff = allowed - needed
    if reverse_diff:
        print(f"(Needed) '{file}' doesn't contain allowed symbols: {reverse_diff}")

    unneeded = unneeded & reverse_diff

if unneeded:
    print(f"(Needed) WARNING: no file needed allowed symbols {unneeded} consider removing from allowed list")
