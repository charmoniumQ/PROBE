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

| Work | Issue? | Publication |
|-|-|-|
| SPADEv2 | process-granularity | Table 3 of [Gehani et al.](10.1007/978-3-642-35170-9_6) |
| Hi-Fi | ? | [Pohly et al.](https://doi.org/10.1145/2420950.2420989) |
| LPM | ? | [Bates et al.](https://dl.acm.org/doi/proceedings/10.5555/2831143) |
| KCAL | modify file data | [Ma et al.](https://www.usenix.org/system/files/conference/atc18/atc18-ma-shiqing.pdf) |

If it is precise, what algorithm does it use?

[Bates et. al](https://dl.acm.org/doi/proceedings/10.5555/2831143) does not say exactly, but in a different algorithm, they write `FindSuccessors(Entity)`: This function performs a provenance graph traversal to obtain the list of data objects derived from `Entity`. This is exactly the operation I am trying to speed up.
