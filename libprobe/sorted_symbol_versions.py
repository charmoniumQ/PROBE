import pathlib
import elftools.elf.elffile
import sys
import typing

_T = typing.TypeVar("_T")
def expect_type(typ: type[_T], data: typing.Any) -> _T:
    if not isinstance(data, typ):
        raise TypeError(f"Expected type {typ} for {data}")
    return data

path = sys.argv[1]

symbols = []

with pathlib.Path(path).open("rb") as stream:
    elf_parsed = elftools.elf.elffile.ELFFile(stream)
    sections = {
        section.name: section
        for section in elf_parsed.iter_sections()
    }
    for symbol_idx, symbol in enumerate(sections[".dynsym"].iter_symbols()):
        version_idx = sections[".gnu.version"].get_symbol(symbol_idx).entry["ndx"]
        version_pair = sections[".gnu.version_r"].get_version(version_idx)
        if version_pair is not None:
            version, version_aux = sections[".gnu.version_r"].get_version(version_idx)
            lib_file_name = version.name
            version_name, _, version_string = version_aux.name.rpartition("_")
            try:
                version_num = tuple(map(int, version_string.split(".")))
            except ValueError:
                version_num = ()
            symbols.append((lib_file_name, version_num, version_aux.name, expect_type(str, symbol.name)))
        else:
            symbols.append((version_idx, (), "", symbol.name))


def is_inty(string: str) -> bool:
    try:
        int(string)
    except ValueError:
        return False
    else:
        return True


def symbol_version_key(version_name: str) -> typing.Any:
    return tuple(
        tuple(
            int(dotted_segment) if is_inty(dotted_segment) else dotted_segment
            for dotted_segment in underscored_segment.split(".")
        )
        for underscored_segment in version_name.split("_")
    )


for lib_file_name, _, version_name, symbol_name in sorted(symbols, key=lambda tup: symbol_version_key(tup[2])):
    print(lib_file_name, version_name, symbol_name)
