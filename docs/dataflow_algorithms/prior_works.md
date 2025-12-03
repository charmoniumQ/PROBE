Consider the following program trace:

```
open(A, read only);
...
close(A);
...
open(B, write only);
...
close(B);
...
open(C, read only);
...
close(C);
```

Can information flow from C to B? No, because all writes of B happen before all reads of C.

Such a process trace would be generated whenever one program that implements multiple tasks, each with their own input and output. A false dependency, such as C -> B, means that the system will either not be able delete C or not know that it can reproduce B.

In order to resolve the false dependency, one needs to record a list of read/write events not just read/write sets. Note that open/close are considered read/write events, for the sake of this writing. If a process manipulates the same file more than once (open, close, ..., open, close), then the read/write event recording will incur more overhead. In practice, the appending to a list is not that much worse than adding to a set; the only added cost is at analysis-time, which can happen offline.

On the other hand, some provenance tracers go to an even finer grain, using binary analysis to reason about the propagation of information from a file reads and to file writes.

| Work                       | Reduction strategy               | Publication                                                                                                |
|----------------------------|----------------------------------|------------------------------------------------------------------------------------------------------------|
| SPADEv2                    | none beyond process-granularity  | Table 3 of [Gehani et al. 2012](https://doi.org/10.1007/978-3-642-35170-9_6)                               |
| Hi-Fi                      | not described                    | [Pohly et al. 2012](https://doi.org/10.1145/2420950.2420989)                                               |
| LPM                        | not described                    | [Bates et al. 2015](https://www.usenix.org/system/files/conference/usenixsecurity15/sec15-paper-bates.pdf) |
| KCAL                       | modify file data                 | Sec. 3.1 of [Ma et al. 2018](https://www.usenix.org/system/files/conference/atc18/atc18-ma-shiqing.pdf)    |
| LogGC                      | seemingly, total order on events | Fig. 2 of [Lee et al. 2013](http://doi.org/10.1145/2508859.2516731)                                        |
| CPR/PCAR                   | global, monotonic clock          | Sec. 3 of [Xu et al. 2016](https://doi.org/10.1145/2976749.2978378)                                        |
| ProTracer                  | taint tracking TODO              | [Ma et al. 2016](https://doi.org/10.14722/ndss.2016.23350)                                                 |
| NodeMerge                  |                                  | [Tang et al. 2018](https://doi.org/10.1145/3243734.3243763)                                                |
|                            |                                  | [Hossain et al. 2018](https://www.usenix.org/system/files/conference/usenixsecurity18/sec18-hossain.pdf)   |
| Why-Across-Time Provenance | formalism; Watermelon?           | [Whittaker et al. 2018](https://doi.org/10.1145/3267809.3267839)                                           |

If it is precise, what algorithm does it use?

[Bates et. al](https://dl.acm.org/doi/proceedings/10.5555/2831143) does not say exactly, but in a different algorithm, they use `FindSuccessors(Entity)` as a primitive, explaining "This function performs a provenance graph traversal to obtain the list of data objects derived from `Entity`". This is exactly the operation I am trying to speed up.

# Part 2

If provenance tracer operates within the kernel and records every read and write, events touching the same file can be made atomic and totally ordered. If you move outside the kernel, but into a centralized process, it is likewise possible to make events atomic and totally ordered. However, if each process logs its own provenance at its own pace, the accesses become non-atomic and only partially-ordered. Even a single system has to be treated as a distributed one, due to process-level parallelism.

If events are only partially ordered, it is unclear which access is responsible for the current version of a file, because we do not know which access is "last". One could iterate the HB graph in reverse topological order, but in the worst case, you would have to look at all nodes in the graph (see example), O(V + E).

Example: 100 processes, as vertical lines; time goes downwards. One process touches the file. We still have to look through every other process to see if it touches the file.

If you had to answer many of these queries, it may be better to create an information flow graph first.
