# libprobe

Required reading: <https://matt.sh/howto-c>

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

# C lints

- https://github.com/include-what-you-use/include-what-you-use
- https://code.google.com/archive/p/cppclean
- Clang-analyzer
- Clang-tidy
