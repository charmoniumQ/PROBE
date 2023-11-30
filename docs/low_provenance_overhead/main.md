## Background

- Define provenance: "a record of the ultimate origin and passage of an item through its previous owners." (Oxford English Dictionary)
- Define computational provenance: the input files (usually software programs, configuration files, and data) used to generate a specific artifact.
- Define system-level [computational] provenance: modifying the system to collect provenance (as opposed to the application, workflow engine, or programming language).
  - System-level provenance is the easies to apply, but least semantically rich.
- Define same-architecture portability problem: software runs on one machine, how to transport it to another machine with the same architecture?
- Classical solutions to same-architecture portability involve performance overheads or are hard-to-use:
  - VMs (performance overhead and intrusive)
  - Use only portable programming languages (performance overhead)
  - Docker (intrusive)
  - Nix/Guix (modifies the user's workflow)
  - Static analysis (string analysis for Java)
  - Debloating


Thesis statement: **Library interposition is a low-overhead way to collect system-level provenance. System-level provenance data can be used to implement low-overhead and transparent same-architecture portability ("killer app").**

## Technical Contribution

### Library interposition is a more efficient way to track provenance

- Prototype that does provenance tracing with library interposition (standard and de facto standard)
- Falls back on SaBRe, FUSE, or ptrace
- Create archive containing all input files and Makefile which generates output files
- Use heuristics to defer to packages for certain files

### Completeness analysis

### Performnace analysis

- Introduce performance model
- Compare recording/tracing overhead
- Compare replaying overhead
- Compare storage overhead

## Future work

- Future optimiations
  - Optimizations in capturing
  - Storage optimizations
- Alternative methods which increase coverage
- Alternative applications
  - Artifact description
  - Transitive credit
  - Incremental computation

## Conclusion
