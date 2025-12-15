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
) -> None:
    n_levels = len(log_lengths)
    log_length = sum(log_lengths)
    log_length_rounded = (
        16 if log_length <= 16 else
        32 if log_length <= 32 else
        64 if log_length <= 64 else
        96 if log_length <= 96 else 
        raise_(ValueError("Cannot go bigger than 64 log_lengths"))
    )

    # Calculate masks, shifts, and log_lengths
    shifts = [
        log_length - sum(log_lengths[:i+1])
        for i in range(n_levels)
    ]
    masks = [
        ((1 << bit_length) - 1) << shift
        for bit_length, shift in zip(log_lengths, shifts)
    ]
    lengths = [
        1 << bit_length
        for bit_length in log_lengths
    ]
    sizeof_pointer = 16
    sizeof_one_entry = sum([length * sizeof_pointer for length in lengths])

    # Assert no two masks overlap
    for mask0, mask1 in itertools.combinations(masks, 2):
        assert mask0 & mask1 == 0, f"Masks overlap {mask0} {mask1}"

    total = 0
    for mask in masks:
        total |= mask
    assert total == (1 << log_length) - 1, "Masks don't add up:\n" + "\n".join(
        f"{mask << shift:0{log_length}b}"
        for mask, shift in zip(masks, shifts)
    )

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
        f"struct _{camel_case}{last_level}Struct {{ _Atomic({value_type}) array [{lengths[last_level]}]; }};",
        *[
            "\n".join([
                f"union _{camel_case}{i}Union {{ struct _{camel_case}{i+1}Struct* ptr; enum _{camel_case}Flag flag; }};",
                f"struct _{camel_case}{i}Struct {{ _Atomic(union _{camel_case}{i}Union) array [{lengths[i]}]; }};",
            ])
            for i in range(last_level - 1, -1, -1)
        ],
        f"struct {camel_case} {{ struct _{camel_case}0Struct inner; }};",
        "",
        f"{fn_attrs} {value_type} {snakecase}_get_or_default(const struct {camel_case}* {snakecase}, {index_type} index, {value_type} def);",
        "",
        f"{fn_attrs} bool {snakecase}_compare_exchange(struct {camel_case}* {snakecase}, {index_type} index, {value_type} expected, {value_type} desired);",
        "",
        f"// sizeof table with one entry = {sizeof_one_entry / 1024:.1f}KiB = {sizeof_one_entry / 1024 / 1024:.1f}MiB",
    ]))
    c_source.write_text("\n".join([
        "#include <sched.h>",
        "#include <stdlib.h>",
        "#include \"../src/debug_logging.h\"",
        f"#include \"{c_header}\"",
        "",
        *[
            f"#define _{upper}{i}_MASK 0x{mask:0{log_length_rounded // 4}x}"
            for i, mask in enumerate(masks)
        ],
        *[
            f"#define _{upper}{i}_SHIFT {shifts[i]}"
            for i, mask in enumerate(masks)
        ],
        "",
        f"{value_type} {snakecase}_get_or_default(const struct {camel_case}* {snakecase}, {index_type} index, {value_type} def) {{",
        f"  const struct _{camel_case}0Struct* struct0 = &{snakecase}->inner;",
        "  size_t subindex;",
        *itertools.chain.from_iterable([
            [
                f"  subindex = (index & _{upper}{i}_MASK) >> _{upper}{i}_SHIFT;",
                f"  const union _{camel_case}{i}Union union{i} = atomic_load(&*struct{i}.array[subindex]);",
                f"  if (union{i}.flag == _{upper}_UNALLOCATED || union{i}.flag == _{upper}_WAITING) {{ return def; }}",
                f"  const struct _{camel_case}{i+1}Struct* struct{i+1} = union{i}.ptr;",
                "",
            ]
            for i in range(last_level)
        ]),
        f"  subindex = (index & _{upper}{last_level}_MASK) >> _{upper}{last_level}_SHIFT;",
        f"  {value_type} ret = atomic_load(&*struct{last_level}.array[subindex]);",
        "  return ret;",
        "}",
        "",
        f"bool {snakecase}_compare_exchange(struct {camel_case}* {snakecase}, {index_type} index, {value_type} expected, {value_type} desired) {{",
        f"  struct _{camel_case}0Struct* struct0 = &{snakecase}->inner;"
        "  size_t subindex;",
        *itertools.chain.from_iterable([
            [
                f"  subindex = (index & _{upper}{i}_MASK) >> _{upper}{i}_SHIFT;",
                f"  union _{camel_case}{i}Union expected{i} = {{ .flag = _{upper}_UNALLOCATED }};",
                f"  union _{camel_case}{i}Union desired{i} = {{ .flag = _{upper}_WAITING }};",
                f"  struct _{camel_case}{i+1}Struct* struct{i+1};",
                f"  if (atomic_compare_exchange_strong(&struct{i}->array[subindex], &expected{i}, desired{i})) {{",
                f"    struct{i+1} = expected{i}.ptr = EXPECT_NONNULL(calloc(sizeof(struct _{camel_case}{i+1}Struct), 1));",
                f"    atomic_store(&struct{i}->array[subindex], expected{i});",
                "  } else {",
                f"    while (expected{i}.flag == 1) {{ expected{i} = atomic_load(&struct{i}->array[subindex]); }}",
                f"    struct{i+1} = expected{i}.ptr;",
                "}",
                "",
            ]
            for i in range(last_level)
        ]),
        f"  subindex = (index & _{upper}{last_level}_MASK) >> _{upper}{last_level}_SHIFT;",
        f"  return atomic_compare_exchange_strong(&struct{last_level}->array[subindex], &expected, desired);",
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
