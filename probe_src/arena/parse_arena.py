#!/usr/bin/env python
from __future__ import annotations
import tarfile
import dataclasses
import pathlib
import ctypes
from typing import Sequence, Iterator, overload

@dataclasses.dataclass(frozen=True)
class MemorySegment:
    buffr: bytes
    start: int
    stop: int

    def __post_init__(self) -> None:
        self._check()

    def _check(self) -> None:
        assert self.stop >= self.start
        assert len(self.buffr) == self.stop - self.start

    @property
    def length(self) -> int:
        return self.stop - self.start

    @overload
    def __getitem__(self, idx: slice) -> bytes: ...

    @overload
    def __getitem__(self, idx: int) -> int: ...

    def __getitem__(self, idx: slice | int) -> bytes | int:
        if isinstance(idx, slice):
            if not (self.start <= idx.start <= idx.stop <= self.stop):
                raise IndexError()
            return self.buffr[idx.start - self.start : idx.stop - self.start : idx.step]
        elif isinstance(idx, int):
            return self.buffr[idx - self.start]
        else:
            raise TypeError("Invalid index type")

    def __contains__(self, idx: int) -> bool:
        return self.start <= idx < self.stop

    def overlaps(self, other: MemorySegment) -> bool:
        return any((
            self.start <= other.start < self.stop,
            self.start <= other.stop < self.stop,
            other.start <= self.start < other.stop,
            # other.start <= self.end < other.end, # redundant case
        ))

    def __repr__(self) -> str:
        return f"Memory(..., {self.start:08x}, {self.stop:08x})"


@dataclasses.dataclass(frozen=True)
class MemorySegments:
    segments: Sequence[MemorySegment]

    def __post_init__(self) -> None:
        self._check()

    def _check(self) -> None:
        assert sorted(self.segments, key=lambda segment: segment.start) == self.segments

    @overload
    def __getitem__(self, idx: slice) -> bytes: ...

    @overload
    def __getitem__(self, idx: int) -> int: ...

    def __getitem__(self, idx: slice | int) -> bytes | int:
        if isinstance(idx, slice):
            buffr = b''
            for segment in self.segments:
                buffr += segment.buffr[max(idx.start, segment.start) - segment.start : min(idx.stop, segment.stop) - segment.start]
            return buffr[::idx.step]
        elif isinstance(idx, int):
            for segment in self.segments:
                if idx in segment:
                    return segment[idx]
            else:
                raise IndexError(idx)
        else:
            raise TypeError("Invalid index type")

    def __contains__(self, idx: int) -> bool:
        return any(idx in segment for segment in self.segments)

    def __iter__(self) -> Iterator[MemorySegment]:
        return iter(self.segments)


class CArena(ctypes.Structure):
    _fields_ = [
        ("instantiation", ctypes.c_size_t),
        ("base_address", ctypes.c_void_p),
        ("capacity", ctypes.c_ulong),
        ("used", ctypes.c_ulong),
    ]


def parse_arena_buffer(buffr: bytes) -> MemorySegment:
    c_arena = CArena.from_buffer_copy(buffr)
    start = c_arena.base_address + ctypes.sizeof(CArena)
    stop = c_arena.base_address + c_arena.used
    return MemorySegment(buffr[ctypes.sizeof(CArena) : c_arena.used], start, stop)


def parse_arena_dir(arena_dir: pathlib.Path) -> MemorySegments:
    memory_segments = []
    for path in sorted(arena_dir.iterdir()):
        assert path.name.endswith(".dat")
        buffr = path.read_bytes()
        memory_segments.append(parse_arena_buffer(buffr))
    return MemorySegments(sorted(memory_segments, key=lambda seg: seg.start))


def parse_arena_dir_tar(
        arena_dir_tar: tarfile.TarFile,
        prefix: pathlib.Path = pathlib.Path(),
) -> MemorySegments:
    memory_segments = []
    for member in sorted(arena_dir_tar, key=lambda member: member.name):
        member_path = pathlib.Path(member.name)
        if member_path.is_relative_to(prefix) and member_path.relative_to(prefix) != pathlib.Path("."):
            assert member.name.endswith(".dat")
            extracted = arena_dir_tar.extractfile(member)
            assert extracted is not None
            buffr = extracted.read()
            memory_segment = parse_arena_buffer(buffr)
            memory_segments.append(memory_segment)
    return MemorySegments(sorted(memory_segments, key=lambda seg: seg.start))


if __name__ == "__main__":
    # Run by `make test`
    import sys
    arena_dir = pathlib.Path(sys.argv[1])
    print(f"Parsing {arena_dir!s}")
    if not arena_dir.exists():
        print(f"{arena_dir!s} doesn't exist")
        sys.exit(1)
    if ".tar" in arena_dir.name:
        arena_dir_tar = tarfile.open(arena_dir)
        print("As a tarfile")
        print(parse_arena_dir_tar(arena_dir_tar, pathlib.Path(sys.argv[2])))
        arena_dir_tar.close()
    else:
        print(parse_arena_dir(arena_dir))
