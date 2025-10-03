import subprocess
import sys

allowed = {
    "_ITM_deregisterTMCloneTable",
    "_ITM_registerTMCloneTable",
    "__confstr_chk",
    "__cxa_finalize",
    "__environ",
    "__errno_location",
    "__gmon_start__",
    "__register_atfork",
    "__stack_chk_fail",
    "__tls_get_addr",
    "__vfprintf_chk",
    "__vsnprintf_chk",
    "calloc",
    "dirfd",
    "dlsym",
    "environ",
    "fileno",
    "free",
    "malloc",
    "memcpy",
    "memset",
    "pthread_getspecific",
    "pthread_key_create",
    "pthread_rwlock_init",
    "pthread_rwlock_rdlock",
    "pthread_rwlock_unlock",
    "pthread_rwlock_wrlock",
    "pthread_setspecific",
    "realloc",
    "stderr",
    "thrd_current",
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
