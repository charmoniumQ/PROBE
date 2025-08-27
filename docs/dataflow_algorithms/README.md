We have a happens-before graph, A->B means A happens-before B, which is the union of program-order, forks, and joins.

How to construct a dataflow graph?

Certainly program-order and forks have dataflow, carrying an entire copy of the process's memory. Joins are also dataflow, as they carry a return integer. While the integer may not seem like much, often its success or failure (non-zero-ness) is really important for the parent's control flow.

How to version repeated accesses to the same inode?

Event-based/sample-schedule: pick a "sample" schedule.

[at_open_algo.py](./at_open_algo.py)

[at_opens_and_closes.py](./at_opens_and_closes.py)

[at_opens_and_closes_with_separate_access.py](./at_opens_and_closes_with_separate_access.py)

Problem with event-based: no individual schedule constructs a sufficiently conservative DFG. Consider the following HB graph

digraph {
  Read of A -> Write of B
  Read of B -> Write of A
}

Any valid schedule will only have one inode dataflow edge. But data could flow from second op of second proc to first op of first proc AND from second of first to first of second. Just not in the same schedule.

It doesn't handle `sh -c "a | b"` elegantly, which has the following graph

digraph {
  open pipe for reading -> open pipe for writing -> fork writer -> fork reader -> wait writer -> wait reader -> close pipe for reading -> close pipe for writing;
  fork writer -> close pipe for reading -> dup pipe for writing to stdout -> close pipe for writing -> exec -> wait writer;
  fork reader -> close pipe for writing -> dup pipe for reading to stdin -> close pipe for reading -> exec -> wait reader;
}

A schedule that puts `write` at the close and `read` at the open will not see dataflow from the writing process to the reading one.

Instead, we take the more complex, "interval" approach.

[interval_algo.py](./interval_algo.py)

[interval_redux.py](./interval_redux.py)

Find the intervals in which a write could have taken place. An interval is for each process, the earliest and latest possible quad in which a read/write may happen.

The logic in `interval_redux.py` for dealing with concurrent segments works if the segments are disjoint.
