## Research reading list

- [_Provenance for Computational Tasks: A Survey_ by Freire et al. in CiSE '08](https://sci.utah.edu/~csilva/papers/cise2008a.pdf) for an overview of provenance in general.

- [_Transparent Result Caching_ by Vahdat and Anderson @ USENIX ATC '98](https://www.usenix.org/legacy/publications/library/proceedings/usenix98/full_papers/vahdat/vahdat.pdf) for an early system-level provenance tracer in Solaris using the `/proc` fs. Linux's `/proc` fs doesn't have the same functionality. However, this paper discusses two interesting application of provenance: unmake  (query lineage information) and transparent Make (more generally, incremental computation).

- [_CDE: Using System Call Interposition to Automatically Create Portable Software Packages_ by Guo and Engler @ USENIX ATC '11](https://www.usenix.org/legacy/events/atc11/tech/final_files/GuoEngler.pdf) for an early system-level provenance tracer. Their only application is software execution replay, but replay is quite an important application.

- [_Techniques for Preserving Scientific Software Executions: Preserve the Mess or Encourage Cleanliness?_ by Thain, Meng, and Ivie @ iPRES 2015 ](https://curate.nd.edu/articles/journal_contribution/Techniques_for_Preserving_Scientific_Software_Executions_Preserve_the_Mess_or_Encourage_Cleanliness_/24824439?file=43664937) discusses whether enabling automatic-replay is actually a good idea. A cursory glance makes PROBE seem more like "preserving the mess", but I think, with some care in the design choices, it actually can be more like "encouraging cleanliness", for example, by having heuristics that help cull/simplify provenance and generating human readable/editable package-manager recipes.

- [_SoK: History is a Vast Early Warning System: Auditing the Provenance of System Intrusions_ by Inam et al. @ SOSP '23](https://adambates.org/documents/Inam_Oakland23.pdf) see specifically Inam's survey of different possibilities for the "Capture layer", "Reduction layer", and "Infrastructure layer". Although provenance-for-security has different constraints than provenacne for other purposes, the taxonomy that Inam lays out is still useful. PROBE operates by intercepting libc calls, which is essentially a "middleware" in Table I (platform modification, no program modification, no config change, incomplete mediation, not tamperproof, inter-process tracing, etc.).

- [_System-Level Provenance Tracers_ by me et al. @ ACM REP 2023](./docs/acm-rep-pres.pdf) for a motivation of this work. It surveys prior work, identifies potential gaps, and explains why I think library interposition is a promising path for future research.

- [_Computational Experiment Comprehension using Provenance Summarization_ by Bufford et al. @ ACM REP 2023](https://dl.acm.org/doi/pdf/10.1145/3641525.3663617) discusses how to implement an interface for querying provenance information. They compare classical graph-based visualization with an interactive LLM in a user-study.

## Prior art

- [RR-debugger](https://github.com/rr-debugger/rr) which is much slower, but features more complete capturing, lets you replay but doesn't let you do any other analysis.

- [Sciunits](https://github.com/depaul-dice/sciunit) which is much slower, more likely to crash, has less complete capturing, lets you replay but doesn't let you do other analysis.

- [Reprozip](https://www.reprozip.org/) which is much slower and has less complete capturing.

- [CARE](https://proot-me.github.io/care/) which is much slower, has less complete capturing, and lets you do containerized replay but not unpriveleged native replay and not other analysis.

- [FSAtrace](https://github.com/jacereda/fsatrace) which is more likely to crash, has less complete capturing, and doesn't have replay or other analyses.
