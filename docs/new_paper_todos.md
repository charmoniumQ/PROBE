**Tasks before resubmitting "performance of provenance" paper**:

1. Refactor technical debt in PROBE. Already have a branch with refactoring complete, but need to sync it up, merge it, and rebase current branches onto it
2. Fix broken benchmarks and provenance tracers
3. Look into benchmark non-determinism: faketime, aslr, taskset, machine id, file cache rerun, clear cache.
4. Implement more benchmarks.
5. Create statistics described here: https://github.com/users/charmoniumQ/projects/1/views/1?pane=issue&itemId=94217621
6. Note "actively maintained"
7. Run SSH remotely
8. Review:
   - https://gernot-heiser.org/benchmarking-crimes.html
   - https://www2.sigsoft.org/EmpiricalStandards/docs/standards?standard=Benchmarking

**Tasks before writing "Measuring the level of determinism in common record/replay tools" paper**:

1. Capture shared libraries on exec in libprobe. This improves the "completeness" claim, captures the same files as captured by other record/replay.
2. Create a "impact of non-determinism" table:
  1. In the previous benchmark suite, how many workloads are bit-wise reproducible.
  2. For each non-deterministic input, manipulate the input, how many previously bit-wise reproducible workloads are still bit-wise reproducible. This determines its "probability of this non-det input impacting output."
3. Create a "determinism completeness table" showing whether each tool (columns) records-and-replays, stabilizes, or detects each particular non-deterministic input (rows). Validate this with an application (could be synthetic) whose output is deterministic for the "yesses" and non-deterministic for the "noes". At the end of each column, what proportion of benchmarks only depended on the "yesses" for that column?
   - Recording-and-replaying an input := record value is unchanged from native execution, replay value uses the recorded value.
   - Stabalizing an input := changing the record and replay to have the same value.
   - Detecting an input := detecting when the program accesses a particular input (neither stabalizing nor recording-and-replaying it).
4. Create a "portability table" whose rows are pairs <platform on which recording was done, platform on which replaying was done> and columns are whether record/replay X allows it, allows it reproducibly, or disallows it.
5. Statically link libprobe. Statically linking would improve the portability claims.
6. Fix arena allocator. This avoids running out of memory while tracing big applications.
7. Detect if the process loads a library or executable that may bypass PROBE (static binary analysis).
8. Capture more ops in libprobe. Also improves completeness.

**Tasks before presenting applications**:

1. Debug OCI image recording of Python
2. Debug multiple extraneous versions appearing the dataflow graph
3. Include symlinks properly in dataflow graph.
4. Compute and store DFG at transcription time. Currently this is a separate command because transcription is (and must be for compatibility) implemented in Rust while DFG is implemented in Python.
5. DFG should be based on persistent provenance
6. Develop heuristics for converting provenance graph to a run script.

**Tasks for user-study**:

1. Determine task, efficiency, and correctness for each task:
   1. **Containerization**: Given this paper's repository, convert it to a container image, using or not using PROBE. Correctness is determined by if the container image produces the output _de novo_. Efficiency is determined by human time.
   2. **Workflow-ization**: Given this paper's repository, convert the pile-of-scripts to a workflow, using or not using PROBE. Correctness is determined by if the workflow produces the right output, given a change to particular inputs. Efficiency is determined by human time and AST complexity of workflow.
   3. **Comprehension/incremental computation**: Set of problems like "A.txt an input to Z.png?" in this codebase given or not given a PROBE DFG. Efficiency is determined by human time. Efficiency is determined by human time.
   4. **Portability**: Rerun this procedure on a new machine, given or not given a PROBE artifact. Efficiency is determined by human time.
2. Develop interview questions.
3. Develop procedure: Each task will have A instances and B instances. Participants will be divided into A-then-B vs B-then-A; and PROBE-then-nothing vs nothing-then-PROBE. Statistics will be computed in each of the four blocks.
4. Do IRB.
5. Pilot experiment.
6. Execute experiment.

**For paper on "Extensions to Workflow Run Crate for record/replay"**:

1. PROBE record should output interoperable provenance (Workflow Run Crate)
2. PROBE applications (create workflow, create container, etc.) should input interoperable provenance (Workflow Run Crate or W3C PROV)
3. Define constraints (SHACL or ShEx) for Workflow Run Crate data for which the applications will succeed.
4. Prove that our output satisfies the constraints; prove that the constraints are sufficient for the applications to succeed.

