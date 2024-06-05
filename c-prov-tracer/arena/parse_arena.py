#!/usr/bin/env python
from __future__ import annotations
import dataclasses
import pathlib
import ctypes
import typing


@dataclasses.dataclass(frozen=True)
class MemorySegment:
    buffr: bytes
    start: int
    stop: int

    def __post_init__(self) -> None:
        self._check()

    def _check(self) -> None:
        assert self.stop > self.start
        assert len(self.buffr) == self.stop - self.start

    @property
    def length(self) -> int:
        return self.stop - self.start

    @typing.overload
    def __getitem__(self, idx: slice) -> bytes: ...

    @typing.overload
    def __getitem__(self, idx: int) -> int: ...

    def __getitem__(self, idx: slice | int) -> bytes | int:
        if isinstance(idx, slice):
            if not (self.start <= idx.start <= idx.stop <= self.stop):
                raise IndexError()
            return self.buffr[idx.start - self.start : idx.stop - self.start : idx.step]
        elif isinstance(idx, int):
            return self.buffr[idx - self.start]

    def __contains__(self, idx: int) -> bool:
        return self.start <= idx < self.stop

    def overlaps(self, other: MemorySegment) -> bool:
        return any((
            self.start <= other.start < self.stop,
            self.start <= other.stop < self.stop,
            other.start <= self.start < other.stop,
            # other.start <= self.end < other.end, # redundant case
        ))


@dataclasses.dataclass(frozen=True)
class MemorySegments:
    segments: typing.Sequence[MemorySegment]

    def __post_init__(self) -> None:
        self._check()

    def _check(self) -> None:
        assert not any(
            segment_a.overlaps(segment_b)
            for a, segment_a in enumerate(self.segments)
            for segment_b in self.segments[a + 1:]
        )
        assert sorted(self.segments, key=lambda segment: segment.start) == self.segments

    @typing.override
    def __getitem__(self, idx: slice) -> bytes: ...

    @typing.override
    def __getitem__(self, idx: int) -> int: ...

    def __getitem__(self, idx: slice | int) -> bytes | int:
        if isinstance(idx, slice):
            buffr = b''
            for segment in self.segments:
                buffr += segment.buffr[max(idx.start, segment.start) - segment.start : min(idx.stop, segment.stop) - segment.start]
            return buffr[::idx.step]
        else:
            for segment in self.segments:
                if idx in segment:
                    return segment[idx]
            else:
                raise IndexError(idx)

    def __contains__(self, idx: int) -> bool:
        return any(idx in segment for segment in self.segments)


class CArena(ctypes.Structure):
    _fields_ = [
        ("instantiation", ctypes.c_size_t),
        ("base_address", ctypes.c_void_p),
        # echo -e '#include <stdint.h>\n' | cpp | grep uinptr_t
        ("capacity", ctypes.c_ulong),
        ("used", ctypes.c_ulong),
    ]


def parse_arena_dir(arena_dir: pathlib.Path) -> typing.Sequence[MemorySegment]:
    memory_segments = list[MemorySegment]()
    for path in sorted(arena_dir.iterdir()):
        assert path.name.endswith(".dat")
        buffr = path.read_bytes()
        c_arena = CArena.from_buffer_copy(buffr)
        start = c_arena.base_address + ctypes.sizeof(CArena)
        stop = c_arena.base_address + c_arena.used
        memory_segments.append(MemorySegment(buffr[ctypes.sizeof(CArena) : c_arena.used], start, stop))
    return memory_segments


if __name__ == "__main__":
    import sys
    arena_dir = pathlib.Path(sys.argv[1])
    print(f"Parsing {arena_dir!s}")
    if not arena_dir.exists():
        print(f"{arena_dir!s} doesn't exist")
        sys.exit(1)
    print(parse_arena_dir(arena_dir))
