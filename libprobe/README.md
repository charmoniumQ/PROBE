# libprobe

Required reading: <https://matt.sh/howto-c>

# Intercepting a new op

- Look in `generator/libc_source_hooks.c`
- Copy the structure there

# Refresh the compile_commands.json

``` sh
make clean && make compile_commands.json
```

# C source checks

- Don't use `__` to mark private variables; it's ugly and they will have hidden visibility by default.

- See if global variables can be converted to static function variables (same lifetime, but scoped to the function).

- Include its own header first.

- Apply `nonnull` attribute liberally.

- All functions should be `static inline` (only used in this .c file and small), `static` (same but large), or nothing (in which case, visibility should be defined in header).

# C header checks

- Always begin with `#pragma once`.

- All functions should be `__attribute__((visibility("hidden")))` if used elsewhere in the project or `__attribute__((visibility("default")))` if exported to public API.

- Ensure `nonnull` and `returns_nonnull` are applied where applicable.

# Run C lints

``` sh
make format

make check

make deep-check

# https://github.com/NixOS/nixpkgs/pull/395967
# https://clang.llvm.org/docs/analyzer/user-docs/CommandLineUsage.html#codechecker
# https://github.com/Ericsson/codechecker/blob/master/docs/usage.md
# TODO: make CodeChecker work
CodeChecker analyze compile_commands.json -o reports
```

Unfortunately [include-what-you-use](https://github.com/include-what-you-use/include-what-you-use), it often suggests "private/implementation-defined" headers like `linux/limits.h` rather than the [documented public interface `limits.h`](https://www.man7.org/linux/man-pages/man0/limits.h.0p.html). For those cases, I overrode those wrong cases with the comment; search `IWYU pragma` to see examples.
