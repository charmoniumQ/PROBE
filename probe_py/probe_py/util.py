import abc
import collections
import getpass
import grp
import heapq
import itertools
import os
import pathlib
import tarfile
import time
import typing


def get_umask() -> int:
    old_umask = os.umask(0o644)
    os.umask(old_umask)
    return old_umask


def default_tarinfo(path: pathlib.Path | str) -> tarfile.TarInfo:
    return tarfile.TarInfo(name=str(path)).replace(
        mtime=int(time.time()),
        mode=get_umask(),
        uid=os.getuid(),
        gid=os.getgid(),
        uname=getpass.getuser(),
        gname=grp.getgrgid(os.getgid()).gr_name,
    )


def filter_relative_to(path: pathlib.Path) -> typing.Callable[[tarfile.TarInfo], tarfile.TarInfo]:
    def filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
        member_path = pathlib.Path(member.name)
        return member.replace(name=str(member_path.relative_to(path)))
    return filter


_T = typing.TypeVar("_T")
_U = typing.TypeVar("_U")
_V = typing.TypeVar("_V")


def groupby_dict(
        data: typing.Iterable[_T],
        key_func: typing.Callable[[_T], _V],
        value_func: typing.Callable[[_T], _U] = typing.cast(typing.Callable[[_T], _U], lambda x: x),
) -> typing.Mapping[_V, typing.Sequence[_U]]:
    ret: dict[_V, list[_U]] = {}
    for key, group in itertools.groupby(data, key_func):
        ret.setdefault(key, []).extend(map(value_func, group))
    return ret


def all_unique(elements: typing.Iterable[_T]) -> bool:
    return len(set(elements)) == len(list(elements))


def duplicates(elements: typing.Iterable[_T]) -> typing.Iterable[_T]:
    return [
        elem
        for elem, count in collections.Counter(elements).most_common()
        if count > 1
    ]


def decode_nested_object(
        obj: typing.Any,
) -> typing.Any:
    """Converts the bytes in a nested dict to a string"""
    if isinstance(obj, dict):
        return {
            decode_nested_object(key): decode_nested_object(value)
            for key, value in obj.items()
        }
    elif isinstance(obj, (set, list, tuple)):
        return [
            decode_nested_object(elem)
            for elem in obj
        ]
    elif isinstance(obj, bytes):
        return obj.decode(errors="surrogateescape")
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        raise TypeError(f"{type(obj)}: {obj}")


class Comparable(typing.Protocol):
    """Protocol for annotating comparable types."""

    @abc.abstractmethod
    def __lt__(self, other: typing.Self, /) -> bool:
        ...


_Priority = typing.TypeVar("_Priority", bound=Comparable)
_Task = typing.TypeVar("_Task", bound=collections.abc.Hashable)


class PriorityQueue(typing.Generic[_Task, _Priority]):
    """Minimum-priority queue

    Use getitem and getitem to view and change a task's priority.

    Get/set priority implies an additional constraint that each task can only be
    in the queue once, and also the tasks should be hashable.

    If the priorities are equal, order of extraction is order of insertion.

    This is a min-priority queue not a max-priority queue due to heapq. I won't
    implement a `reverse=True`, because as it stands, the priority need not be a
    number; it is an arbtrary `Comparable` type and may not have a negation
    operation.

    https://docs.python.org/3/library/heapq.html#priority-queue-implementation-notes

    """

    _heap: list[tuple[_Priority, int, _Task]]
    _priorities: dict[_Task, tuple[_Priority, int]]
    _removed: set[int]
    _counter: int = 0

    def __init__(
            self,
            initial: typing.Iterable[tuple[_Task, _Priority]] = (),
    ) -> None:
        self._heap = []
        self._priorities = {}
        self._removed = set()
        for task, priority in initial:
            if task in self._priorities:
                raise RuntimeError(f"{task} is in the initial queue twice")
            else:
                self._heap.append((priority, self._counter, task))
                self._priorities[task] = (priority, self._counter)
                self._counter += 1
        heapq.heapify(self._heap)

    def add(self, task: _Task, priority: _Priority) -> None:
        if task in self._priorities:
            raise RuntimeError(f"{task} is already in priority queue")
        else:
            self._priorities[task] = (priority, self._counter)
            heapq.heappush(self._heap, (priority, self._counter, task))
            self._counter += 1

    def pop(self) -> tuple[_Priority, _Task]:
        counter = None
        while counter is None or counter in self._removed:
            priority, counter, task = heapq.heappop(self._heap)
        return priority, task

    def __bool__(self) -> bool:
        while self._heap and self._heap[0][1] in self._removed:
            heapq.heappop(self._heap)
        return bool(self._heap)

    def __delitem__(self, task: _Task) -> None:
        _, counter = self._priorities[task]
        del self._priorities[task]
        self._removed.add(counter)

    def __getitem__(self, task: _Task) -> _Priority:
        return self._priorities[task][0]

    def __setitem__(self, task: _Task, priority: _Priority) -> None:
        del self[task]
        self.add(task, priority)
