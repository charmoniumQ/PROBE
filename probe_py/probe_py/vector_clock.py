from __future__ import annotations
from collections.abc import Iterable as It, Mapping as Map
import charmonium.time_block
import dataclasses
import numpy
import typing
import networkx
from . import partial_order

_ThreadId = typing.NewType("_ThreadId", int)
_TimeVal: typing.TypeAlias = numpy.int16


# TODO: use Numpy arrays


@dataclasses.dataclass
class VectorTime:
    clocks: numpy.ndarray

    def increment(self, current_thread: _ThreadId, predecessors: It[VectorTime]) -> VectorTime:
        "Increment the current_clock, such that it will be after all predecessors"
        max_thread = max(
            current_thread + 1,
            max(len(pred) for pred in predecessors) if predecessors else 0,
        )
        ret = numpy.zeros(max_thread, dtype=_TimeVal)
        ret[:len(self)] = self.clocks
        ret[current_thread] += 1
        for pred in predecessors:
            numpy.maximum(ret[:len(pred)], pred.clocks, out=ret[:len(pred)])
        return VectorTime(ret)

    def __le__(self, other: VectorTime) -> bool:
        common = min(len(self), len(other))
        return bool(
            numpy.all(self.clocks[:common] <= other.clocks[:common])
            and numpy.all(self.clocks[common:] == 0)
            and numpy.all(0 <= other.clocks[common:])
        )

    def __len__(self) -> int:
        return len(self.clocks)

    @staticmethod
    def empty() -> VectorTime:
        return VectorTime(numpy.zeros(0, dtype=_TimeVal))


def upper_bound(times: It[VectorTime]) -> VectorTime:
    ret = numpy.zeros(max(len(time) for time in times), dtype=_TimeVal)
    for time in times:
        for thread, time_val in enumerate(time.clocks):
            ret[thread] = max(ret[thread], time_val)
    return VectorTime(ret)


_Node = typing.TypeVar("_Node", bound=typing.Hashable)
_ThreadLabel = typing.TypeVar("_ThreadLabel", bound=typing.Hashable)


@dataclasses.dataclass(frozen=True)
class VectorClockPartialOrder(
        typing.Generic[_Node, _ThreadLabel],
        partial_order.PartialOrder[_Node],
):
    nodes: It[_Node]
    vector_clocks: Map[_Node, VectorTime]
    thread_ids: Map[_ThreadLabel, _ThreadId]

    def leq(self, node0: _Node, node1: _Node) -> bool:
        return bool(self.vector_clocks[node0] <= self.vector_clocks[node1])

    def diameter(self) -> int:
        "The size of the largest antichain"
        return max(self.thread_ids.values()) + 1


@charmonium.time_block.decor(print_start=False)
def from_dag(
        dag: networkx.DiGraph[_Node],
        thread_fn: typing.Callable[[_Node], _ThreadLabel],
) -> VectorClockPartialOrder[_Node, _ThreadLabel]:
    # Last node for each thread.
    # This is needed for garbage collections
    last_node_in_thread = dict[_ThreadLabel, _Node]()
    for node in networkx.topological_sort(dag):
        last_node_in_thread[thread_fn(node)] = node

    thread_ids = dict[_ThreadLabel, _ThreadId]()
    ret = dict[_Node, VectorTime]()
    last_time_in_thread = dict[_ThreadId, VectorTime]()
    max_thread_id = 0
    unused_thread_ids = set[_ThreadId]()
    import tqdm

    for node in tqdm.tqdm(networkx.topological_sort(dag), total=len(dag)):
        thread = thread_fn(node)

        # Convert thread to ID
        if thread in thread_ids:
            thread_id = thread_ids[thread]
            assert thread_id not in unused_thread_ids
            assert thread_id in last_time_in_thread
        else:
            # Birth of new thread
            # Reuse an old ID (if exists unused) or assign new one
            if unused_thread_ids:
                thread_id = min(unused_thread_ids)
                unused_thread_ids.remove(thread_id)
                assert thread_id in last_time_in_thread
            else:
                thread_id = _ThreadId(max_thread_id)
                max_thread_id += 1
                assert thread_id not in set(thread_ids.values())
                last_time_in_thread[thread_id] = VectorTime.empty()
            thread_ids[thread] = thread_id

        last_time_in_thread[thread_id] = ret[node] = last_time_in_thread[thread_id].increment(
            thread_id,
            [ret[predecessor] for predecessor in dag.predecessors(node)],
        )

        # Death of thread.
        # Reuse its id for someone else.
        if node == last_node_in_thread[thread]:
            unused_thread_ids.add(thread_id)

    return VectorClockPartialOrder(
        tuple(dag.nodes()),
        ret,
        thread_ids,
    )
