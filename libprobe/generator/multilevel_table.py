import typing
import itertools


def multilevel_table(
        name: str,
        bit_lengths: typing.Sequence[int],
        value_type: str,
) -> list[str]:
    n_levels = len(bit_lengths)
    total_bit_length = sum(bit_lengths)
    total_bit_length_rounded = (
        16 if total_bit_length <= 16 else
        32 if total_bit_length <= 32 else
        64 if total_bit_length <= 64 else
        raise_(ValueError("Cannot go bigger than 64 bit_lengths"))
    )

    # Calculate masks, shifts, and bit_lengths
    shifts = [
        total_bit_length_rounded - sum(bit_lengths[:i+1])
        for i in range(n_levels)
    ]
    masks = [
        ((1 << bit_length) - 1) << shift
        for bit_length, shift in zip(bit_lengths, shifts)
    ]
    lengths = [
        1 << bit_length
        for bit_length in bit_lengths
    ]

    # Assert no two masks overlap
    for mask0, mask1 in itertools.combinations(masks, 2):
        assert mask0 & mask1 == 0

    # Assert all masks "add up" to total bit_lengths
    total = 0
    for mask in masks:
        total |= mask
    assert total == (1 << total_bit_length) - 1

    sizeof_pointer = 16
    sizeof_one_entry = sum([length * sizeof_pointer for length in lengths])

    # Name, but formatted for a type name
    type_name = name.capitalize()
    const_name = name.upper()
    func_name = name
    struct_names = [f"_{type_name}Lvl{i}" for i in range(n_levels)]
    inner_name = "inner"
    inners_names = [f"inner{i}" for i in range(n_levels)]
    mask_names = [f"_{const_name}_MASK{i}" for i in range(n_levels)]
    shift_names = [f"_{const_name}_SHIFT{i}" for i in range(n_levels)]

    last_level = n_levels - 1
    create_defn = f"{type_name}* {func_name}_create();"
    create_decl = f"{create_defn[:-1]} {{ return EXPECT_NONNULL(calloc(sizeof(struct {struct_names[0]}), 1)); }}"
    index_type = f"uint{total_bit_length_rounded}_t"
    shift_names = [f"_{type_name}_SHIFT{i}" for i in range(n_levels)]
    mask_names = [f"_{type_name}_MASK{i}" for i in range(n_levels)]
    get_or_default_decl = f"{value_type} {func_name}_get_or_default(const {type_name}* table, {index_type} index, {value_type} def);"
    get_or_default_defn = [
        f"{get_or_default_decl[:-1]} {{",
        f"  const struct {struct_names[0]}* {inners_names[0]} = table;",
        *itertools.chain.from_iterable([
            [
                f"  const struct {struct_names[i+1]}* {inners_names[i+1]} = {inners_names[i]}->inner[(index & {mask_names[i]}) >> {shift_names[i]}];",
                f"  if (!{inners_names[i]}) {{ return def; }}",
            ]
            for i in range(last_level)
        ]),
        f"  {value_type} ret = {inners_names[last_level]}->inner[(index & {mask_names[last_level]}) >> {shift_names[last_level]}];",
        "  return ret;",
        "}",
    ]
    set_if_empty_decl = f"{value_type} {func_name}_set_if_empty({type_name}* table, {index_type} index, {value_type} value);"
    set_if_empty_defn = [
        f"{set_if_empty_decl[:-1]} {{",
        "  ASSERTF(value != 0 && value != NULL, \"This function only makes sense with a non-zero value. Otherwise, it would appear empty after being set.\");"
        f"  struct {struct_names[0]}** inner0 = &table;",
        *itertools.chain.from_iterable([
            [
                f"  struct {struct_names[i+1]}** {inners_names[i+1]} = &(*{inners_names[i]})->inner[(index & {mask_names[i]}) >> {shift_names[i]}];",
                f"  if (!*{inners_names[i+1]}) {{ *{inners_names[i+1]} = EXPECT_NONNULL(calloc(sizeof(struct {struct_names[i+1]}), 1)); }}",
            ]
            for i in range(last_level)
        ]),
        f"  {value_type}* ret = &(*{inners_names[last_level]})->inner[(index & {mask_names[last_level]}) >> {shift_names[last_level]}];",
        "  if (!*ret) {{ *ret = value; }}",
        "  return *ret;",
        "}",
    ]
    return [
        "#include <stdint.h>",
        "#include <stdlib.h>",
        "#define EXPECT_NONNULL(x) ((x))",
        "#define ASSERTF(x, y)",
        *[
            f"#define {mask_names[i]} 0x{mask:0{total_bit_length_rounded // 4}x}"
            for i, mask in enumerate(masks)
        ],
        *[
            f"#define {shift_names[i]} {shifts[i]}"
            for i, mask in enumerate(masks)
        ],
        "",
        f"struct {struct_names[last_level]} {{ {value_type} {inner_name} [{lengths[last_level]}]; }};",
        *[
            f"struct {struct_names[i]} {{ struct {struct_names[i+1]}* {inner_name} [{lengths[i]}]; }};"
            for i in range(last_level - 1, -1, -1)
        ],
        f"typedef struct {struct_names[0]} {type_name};",
        f"// sizeof table with one entry = {sizeof_one_entry // 1024}KiB",
        "",
        create_decl,
        *get_or_default_defn,
        *set_if_empty_defn,
    ]


def raise_(exc: Exception) -> typing.NoReturn:
    raise exc


def size(
        bit_lengths: typing.Sequence[int],
        sizeof_value: int = 8,
        sizeof_pointer: int = 8,
) -> int:
    return sum(2**bit_length * sizeof_pointer for bit_length in bit_lengths[:-1]) + 2**bit_lengths[-1] * sizeof_value

# Inode table:
# 32 for inode + 8 dev major + 8 dev minor
# size([8, 8, 16, 16], 8)
# size([8, 8, 11, 11, 10], 8)

# Open-numbering table
# Total number of FDs is 2^63, assume is actually 2^16
# size([8, 8], 2)
