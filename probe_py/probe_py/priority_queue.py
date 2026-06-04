import collections
import heapq
import typing
from . import util


_Priority = typing.TypeVar("_Priority", bound=util.Comparable)
_Task = typing.TypeVar("_Task", bound=collections.abc.Hashable)


class PriorityQueue(typing.Generic[_Task, _Priority]):
    """Minimum-priority queue

    Use getitem and getitem to view and change a task's priority.

    Get/set priority implies an additional constraint that each task can only be
    in the queue once, and also the tasks should be hashable.

    If the priorities are equal, order of extraction is order of insertion.

    This is a min-priority queue not a max-priority queue due to heapq. I won't
    implement a `reverse=True`, because as it stands, the priority need not be a
    number; it is an arbitrary `Comparable` type and may not have a negation
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

    def peek(self) -> tuple[_Priority, _Task]:
        if self:
            return self._heap[0][0], self._heap[0][2]
        else:
            raise StopIteration("Priority queue is emp")

    def pop(self) -> tuple[_Priority, _Task]:
        if self:
            priority, counter, task = heapq.heappop(self._heap)
            return priority, task
        else:
            raise StopIteration("Priority queue is emp")

    def __bool__(self) -> bool:
        while self._heap:
            _priority, counter, _task = self._heap[0]
            if counter in self._removed:
                self._removed.remove(counter)
                heapq.heappop(self._heap)
            else:
                return True
        return False

    def __contains__(self, task: _Task) -> bool:
        return task in self._priorities and self._priorities[task][1] not in self._removed

    def __delitem__(self, task: _Task) -> None:
        if task in self._priorities:
            _, counter = self._priorities[task]
            del self._priorities[task]
            self._removed.add(counter)
        else:
            raise KeyError(f"{task} was not in the priority queue")

    def __getitem__(self, task: _Task) -> _Priority:
        if task in self._priorities:
            return self._priorities[task][0]
        else:
            raise KeyError(f"{task} was not in the priority queue")

    def __setitem__(self, task: _Task, priority: _Priority) -> None:
        if task in self._priorities:
            self._removed.add(self._priorities[task][1])
        heapq.heappush(self._heap, (priority, self._counter, task))
        self._priorities[task] = (priority, self._counter)
        self._counter += 1
