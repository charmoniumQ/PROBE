# libprobe

Required reading: <https://matt.sh/howto-c>

# Refresh the compile_commands.json

``` sh
make clean && bear -- make
```

# C source checks

- Don't use `__` to mark private variables; it's ugly and they will have hidden visibility by default.

- See if global variables can be converted to static function variables.

- Include its own header last.

- Don't duplicate includes already present in headers.

- Apply `nonnull` attribute liberally.

- All functions should be `static inline` (only used in this .c file and small), `static` (same but large), or nothing (in which case, visibility should be defined in header).

# C header checks

- Always begin with `#pragma once`.

- All functions should be `__attribute__((visibility("hidden")))` if used elsewhere in the project or `__attribute__((visibility("default")))` if exported to public API.

# cppclean

Output of cppclean seems wrong
For example,

    src/prov_buffer.h:3: '../include/libprobe/prov_ops.h' does not need to be #included

Howver, we can't foward-declare it because a public function takes a struct Op (by value).
Therefore, we need the struct layout in the header.

# C lints

- https://github.com/include-what-you-use/include-what-you-use
- https://code.google.com/archive/p/cppclean

``` sh
clang-check include/libprobe/* src/* generated/*

make clean && scan-build make

# https://github.com/NixOS/nixpkgs/pull/395967
# https://clang.llvm.org/docs/analyzer/user-docs/CommandLineUsage.html#codechecker
# https://github.com/Ericsson/codechecker/blob/master/docs/usage.md
CodeChecker analyze compile_commands.json -o reports
```

