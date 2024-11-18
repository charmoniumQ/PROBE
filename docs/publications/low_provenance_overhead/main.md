# Measuring the overhead of rootless provenance tracing

## Background

- Define provenance: "a record of the ultimate origin and passage of an item through its previous owners." (Oxford English Dictionary)
- Define computational provenance: the input files (usually software programs, configuration files, and data) used to generate a specific artifact.
- Define system-level [computational] provenance: modifying the system to collect provenance (as opposed to the application, workflow engine, or programming language).
  - System-level provenance is the easiest to apply, but least semantically rich.
- System-level provenance systems: https://www.sandia.gov/app/uploads/sites/210/2023/11/CSRI-2023-proceedings_FINAL.pdf#page=180
  - Specialized hardware? Modified kernel? Root privileges (LSM or kernel module)?

## Technical contributions
- New benchmark
  - Using most of the various benchmarks proposed in prior work
  - Using more applicable provenance tracers
  - Characterizing IO vs CPU workloads
    - Use operational intensity
- New prov tracer

### Library interposition is a more efficient way to track provenance

- Prototype that does provenance tracing with library interposition (standard and de facto standard)
- Falls back on SaBRe, FUSE, or ptrace
- Create archive containing all input files and Makefile which generates output files
- Use heuristics to defer to packages for certain files

### Performnace analysis

- Introduce performance model
- Compare collection overheads
- Compare storage overheads
- Compare querying overheads

## Future work

- Most promising, unexplored methods
- Fast enough for applications?
  - "Always on" or "by need"?
  - Artifact description
  - Transitive credit
  - Incremental computation
  - Reproducibility
  - Makefile-making

## Conclusion

- New benchmarks to easily compare prov tracers on even playing field
- Data on feasibility of prov tracers
- Provenance systems are important for those who value reproducibility.
