import pathlib
import itertools
import typing
import sys


def multilevel_table(
        c_header: pathlib.Path,
        c_source: pathlib.Path,
        name: str,
        value_type: str,
        log_lengths: typing.Sequence[int],
        sizeof_pointer: int = 8,
        sizeof_value: int = 8,
) -> None:
    n_levels = len(log_lengths)
    last_level = n_levels - 1
    log_length = sum(log_lengths)
    log_length_rounded = (
        16 if log_length <= 16 else
        32 if log_length <= 32 else
        64 if log_length <= 64 else
        128 if log_length <= 128 else 
        raise_(ValueError("Cannot go bigger than 64 log_lengths"))
    )
    lowest_bit = [log_length - sum(log_lengths[:i + 1]) for i in range(n_levels)]
    sizeof_one_entry = sum((1 << log_lengths[i]) * sizeof_pointer for i in range(n_levels - 1)) + (1 << log_lengths[last_level]) * sizeof_value

    # Name, but formatted for a type name
    camel_case = "".join(part.capitalize() for part in name.split())
    upper = name.upper().replace(" ", "_")
    snakecase = name.replace(" ", "_")
    last_level = n_levels - 1
    index_type = f"uint{log_length_rounded}_t" if log_length_rounded < 128 else "unsigned __int128"
    fn_attrs = "__attribute__((visibility(\"hidden\")))"
    c_header.write_text("\n".join([
        "#include <stdatomic.h>",
        "#include <stdbool.h>",
        "#include <stdint.h>",
        "",
        f"enum _{camel_case}Flag {{ _{upper}_UNALLOCATED = 0, _{upper}_WAITING }};",
        f"struct _{camel_case}{last_level}Struct {{ _Atomic({value_type}) array [{1 << log_lengths[last_level]}]; }};",
        *[
            "\n".join([
                f"union _{camel_case}{i}Union {{ struct _{camel_case}{i+1}Struct* _Nullable ptr; enum _{camel_case}Flag flag; }};",
                f"struct _{camel_case}{i}Struct {{ _Atomic(union _{camel_case}{i}Union) array [{1 << log_lengths[i]}]; }};",
            ])
            for i in range(last_level - 1, -1, -1)
        ],
        f"struct {camel_case} {{ struct _{camel_case}0Struct inner; }};",
        "",
        f"{fn_attrs} const _Atomic({value_type})* _Nullable {snakecase}_address_of_weak(const struct {camel_case}* _Nonnull {snakecase}, {index_type} index);",
        "",
        f"{fn_attrs} _Atomic({value_type})* _Nonnull {snakecase}_address_of_strong(struct {camel_case}* _Nonnull {snakecase}, {index_type} index);",
        "",
        f"// sizeof table with one entry = {sizeof_one_entry / 1024:.1f}KiB = {sizeof_one_entry / 1024 / 1024:.1f}MiB",
    ]))
    checks = [
        f"  if (index > {1 << log_length - 1}UL) {{ fprintf(stderr, \"%d-bit table not big enough to accomodate %lu\\n\", {log_length}, index); abort(); }}",
        "  _Static_assert(ATOMIC_BOOL_LOCK_FREE, \"\");",
        "  _Static_assert(ATOMIC_POINTER_LOCK_FREE, \"\");",
    ]
    c_source.write_text("\n".join([
        "#include <assert.h>",
        "#include <stdlib.h>",
        "#include \"../src/debug_logging.h\"",
        f"#include \"{c_header.relative_to(c_source.parent)}\"",
        "",
        "#define _BITS(value, low, length) (((((1L << length) - 1L) << low) & value) >> low)",
        "",
        f"const _Atomic({value_type})* _Nullable {snakecase}_address_of_weak(const struct {camel_case}* _Nonnull {snakecase}, {index_type} index) {{",
        *checks,
        f"  const struct _{camel_case}0Struct* struct0 = &{snakecase}->inner;",
        "",
        *itertools.chain.from_iterable([
            [
                f"  const union _{camel_case}{i}Union union{i} = atomic_load(&struct{i}->array[_BITS(index, {lowest_bit[i]}L, {log_lengths[i]}L)]);",
                f"  if (union{i}.flag == _{upper}_UNALLOCATED || union{i}.flag == _{upper}_WAITING) {{ return NULL; }}",
                f"  const struct _{camel_case}{i+1}Struct* struct{i+1} = union{i}.ptr;",
                "",
            ]
            for i in range(last_level)
        ]),
        f"  return &struct{last_level}->array[_BITS(index, {lowest_bit[last_level]}L, {log_lengths[last_level]}L)];",
        "}",
        "",
        f"_Atomic({value_type})* _Nonnull {snakecase}_address_of_strong(struct {camel_case}* _Nonnull {snakecase}, {index_type} index) {{",
        *checks,
        f"  struct _{camel_case}0Struct* struct0 = &{snakecase}->inner;",
        "",
        *itertools.chain.from_iterable([
            [
                f"  union _{camel_case}{i}Union expected{i} = {{ .flag = _{upper}_UNALLOCATED }};",
                f"  union _{camel_case}{i}Union waiting{i} = {{ .flag = _{upper}_WAITING }};",
                f"  struct _{camel_case}{i+1}Struct* struct{i+1};",
                f"  if (atomic_compare_exchange_strong(&struct{i}->array[_BITS(index, {lowest_bit[i]}L, {log_lengths[i]}L)], &expected{i}, waiting{i})) {{",
                f"    struct{i+1} = expected{i}.ptr = EXPECT_NONNULL(calloc(sizeof(struct _{camel_case}{i+1}Struct), 1));",
                f"    atomic_store(&struct{i}->array[_BITS(index, {lowest_bit[i]}L, {log_lengths[i]}L)], expected{i});",
                "  } else {",
                "    size_t i = 0;",
                f"    while (expected{i}.flag == _{upper}_WAITING) {{",
                f"      expected{i} = atomic_load(&struct{i}->array[_BITS(index, {lowest_bit[i]}L, {log_lengths[i]}L)]);",
                "      if (i != 0 && i % 5 == 0) { WARNING(\"Spinning %d times\", ++i); }",
                "      i++;",
                "    }",
                f"    struct{i+1} = expected{i}.ptr;",
                "  }",
                "",
            ]
            for i in range(last_level)
        ]),
        f"  return &struct{last_level}->array[_BITS(index, {lowest_bit[last_level]}L, {log_lengths[last_level]}L)];",
        "}",
    ]))


def raise_(exc: Exception) -> typing.NoReturn:
    raise exc


c_header = pathlib.Path(sys.argv[1])
c_source = pathlib.Path(sys.argv[2])
name = sys.argv[3]
value = sys.argv[4]
ints = list(map(int, sys.argv[5:]))
multilevel_table(c_header, c_source, name, value, ints)
