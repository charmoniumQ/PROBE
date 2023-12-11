# Recording and reproducing software executions with library interposition

## Introduction

Lack of reproducibility in computational experiments undermines the long-term credibility of science and hinders the day-to-day work of researchers.
The ACM defines **reproducibility** as the ability to obtain a measurement with stated precision by a different team using the same measurement procedure, the same measuring system, under the same operating conditions, in the same or a different location on multiple trials \cite{acminc.staffArtifactReviewBadging2020}.
Reproducing the end result, within a tolerance, using a domain-specific metric, on any sufficiently-powerful platforms is the end goal of reproducibility and the subject of reproducibility research.
Being able to reproduce an execution that is identical, with specific exceptions, on the same CPU architecture is a necessary condition for that ultimate end.

The two categories of solutions that predominate today are (1) **sandboxed package management** (Pip, Conda \cite{aaronmeurerCondaCrossPlatform2014}, Spack \cite{gamblinSpackPackageManager2015}, Guix \cite{courtesReproducibleUserControlledSoftware2015}, Nix \cite{bzeznikNixHPCPackage2017}), and (2) **containerization** (Docker, CharlieCloud \cite{priedhorskyCharliecloudUnprivilegedContainers2017}, Singularity \cite{kurtzerSingularityScientificContainers2017}) or **virtualization** (Vagrant, QEMU, VirtualBox).
Both of these types of solutions require significant additional effort from the user, when the user has already installed their software stack on their native system.
A user will need to either imperatively install the software in a new environment (resulting in a Docker image, QCOW2 image) or declaratively write a script (resulting in a Spack package, Nix/Guix derivation, Dockerfile, Vagrantfile, Singularity Definition File) that installs the software in a new environment[^env].
Unfortunately, many practitioners of computational science may not know to use virtualization or containerization when begininning new projects, and even if switching to virtualization or containerization would only take a few hours, many domain scientists are not willing to commit that amount of effort today.

[^env]: The "environment" can refer to a sandboxed software environment, such as that provided by Pip virtualenv, a containerized environment, such as that provided by Docker, or a virtual machine environment, such as that provided by Virtualbox.

A third category of solution for the same-architecture portability of scientific computational experiments is **record/replay** (rr, CDE \cite{guoCDEUsingSystem2011}, ReproZip \cite{chirigatiReproZipComputationalReproducibility2016}, SciUnits \cite{tonthatSciunitsReusableResearch2017}), which requires almost no user-intervention.
In this paradigm, record and replay are two programs, where _record_ runs a user-supplied program with user-supplied inputs and writes a **replay-package**, which contains all of the relevant data, libraries, and executables.
The replay-package can be sent to any machine that the _replayer_ supports. The replayer runs the executable with the data and libraries from the replay-package.
The only user-intervention required to achieve same-architecture portability is that the user must (1) run their executable within the record tool and (2) upload the replay-package to a public location.
The downside of record/replay is that is has historically been slow: recording adds significant overhead to the runtime of the user's program.

This work presents a novel technique for recording in order to accelerate it, and evaluates this novel technique against existing record/replay schemes for performance, portability, and degree-of-reproducibility.

We want to impact domain researchers who create computational scientific experiments and need a way to make those experiments reexecutable, but do not have the time or knowledge to use containerization or virtualization.

<!-- What about provenance? -->

# Background

## Defining "degree of reproducibility"

The ACM definition of **reproducibility** references a measurement procedure, measurement system, and operating conditions.
In order to translate this to computational science, this work will define a "measurement procedure" as executing a program, a "measurement system" as a hardware platform and operating system, and the "operating conditions" as the machine state variables, on which the measurement depends.
In this interpretation, operating conditions have to be set by the agent seeking to reproduce an experiment; in practice, these are difficult for the experiment-authors to identify and communicate, so operating conditions are often overlooked.
Therefore, we will say an experiment is "more reproducible" or "has a greater degree of reproducibility" if it requires fewer operating conditions.
A "reproducibility technique" is a way of augmenting the measurement system, which allows one to observe the same measurement, but requires fewer operating conditions.
A reproducibility technique does not guarantee that the resulting measurement will be reproducible within a certain precision; just that if the resulting measurement was _already_ reproducible within a certain precision, a reproducibility technique reduces the specific operating conditions, so more people can reproduce the measurement more easily.

Operating conditions frequently relate to the file system, for data files and program dependencies.
Naively, the operating conditions for a computational experiment would include an unknown subset of the filesystem; a conservative assumption would be that the entire filesystem _could_ be used by the program, whether not it actually is.
Reproducibility methods reduce this set.
- Sandboxed package managers require the user to explictly specify how to build each software dependency in the operating conditions of the experiment, with the help of a package repository that maps names to instructions.
- Imperative virtualized and containerized methods use the entire filesystem of a "fresh" machine with the operating conditions of the experiment, which is much presumably smaller than the entire filesystem of the experimenter's local machine.
- Declarative virtualized and containerized methods start from a common "base image" of a fresh machine and specify the steps required to transform the fresh file system to one with the proper operating conditions for the experiment.
- Record/replay records the files a particular execution of the program actually accesses.

---

Other operating conditions include:
- State of other machines on the network [DSK: perhaps this should just be anything that is remote but that could affect the run?]
- Current time
- Initial contents of `/dev/random` and `/dev/urandom`

<!--
Machine code instructions can be divided into (1) process-isolated instructions, which only interacts with the state within the current process, and (2) non-process-isolated instructions, which may interact with the state outside the current process.
For example, an `add` instruction only interacts with the virtual memory within the current process.
While this may have side-effects on the outside state of the system, for example modifying the microarchitectural state, heating up the machine, or taking time, these effects are not documented explicitly and rarely intentionally used by legitimate programs for computation.
Instructions which interact with state outside the current process may be single instructions, such as `rdtsc`, but are more often mediated by the operating system through system calls, such as `open` or `fork`. --><!-- TODO: open/fork are not machine instructions! -->

<!--
For a specific technique of making an identical execution, we define the "degree to which the execution is identical" as which parts of the outside system state and which methods of accessing that state are guaranteed to return bit-wise identical results as a previous run, possibly on a different machine.
For example, a certain record/replay technique may guarantee that accessing regular files through `fopen`, `fread`, and 
-->

# Technical Contribution

## Library interposition

What does `LD_PRELOAD` do?

What if program does not use libc?

## System call tracing

# Evaluation

Compared to other record/replay tools, our evaluation shows that our tool has greater performance and portability of the recorder and replayer themselves but does not capture as many sources of non-determinism.

## Performance

The performance of record/replay includes the wall time taken to record, wall time taken to replay, and size of the replay-package.
If wall time taken to record is too great, users may not record frequently enough or at all.
If the wall time taken to replay is to great, downstream users will avoid using the replay-packages in favor of native execution.
If the size of the replay-package is too large, then it will not be easy to distribute.

[DSK: in fault tolerance, there is often a factor "expected faults" that is used to think about how important the cost of fault detection (overhead when running, whether or not a fault exists) is versus the cost of fault recovery (overhead when there is a fault). Is there anything similar that could be used here?]

All of the record/replay tools follow the same usage for any given `$program`, which can be written as:

```bash
$ $record $output_args /tmp/replay-package $program
...

$ $replay $output_args /tmp/replay-package [$program]
...
```

We simply measure time both of these commands and measure the recursive size of `/tmp/replay-package`, which may be a file or directory depending on the record/replay tool.

We use applications from previous publications on workflow provenance.

- Following PASS \cite{muniswamy-reddyProvenanceAwareStorageSystems2006}, PASSv2 \cite{muniswamy-reddyLayeringProvenanceSystems2009}, SPADE \cite{gehaniSPADESupportProvenance2012}, and LPM \cite{batesTrustworthyWholeSystemProvenance2015}, we use the NIH National Institute of Health's (NIH) National Center for Biotechnology Information (NCBI) Basic Local Alignment Search Tool (BLAST) \cite{altschulBasicLocalAlignment1990}. BLAST is a genomics tool that finds regions of similarity between nucleotide or protein sequences. We use the test queries and data from real-world usage of the tool that were used by Bates' evaluation of LPM \cite{coulourisFiehnLabBlast2016}; the other publications do not specific their data.

- Following PASSv2 \cite{muniswamy-reddyLayeringProvenanceSystems2009}, SPADE \cite{gehaniSPADESupportProvenance2012}, Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}, and LPM \cite{batesTrustworthyWholeSystemProvenance2015}, we use compiling Linux from source as a benchmark with the default configuration. [DSK: I expect that this depends on the version of Linux in some sense, which perhaps depends on the date of the work too]


- Following the First Provenance Challenge \cite{moreauSpecialIssueFirst2008} and its 16 entrants (too many to list here), we use the fMRI workflow described by Moreau.

- Kaggle

- FIE and VIC from Sciunits

## Portability of recorder and replayers

Rr's recorder requires the kernel parameter `kernel.perf_event_paranoid=1`, which requires superuser privelege to set.
An approach which does not require superuser privelege would be more portable.

Using `ptrace` inside a container requires `CAP_SYS_PTRACE`, which is turned off by default.

- Record as normal user
- Record/replay in container

## Sources of non-determinism

# Prior work

- Library interposition
  - fsatrace
  - OPUS
  - Darshan
  - TREC

- Record/replay tools
  - TREC
  - Reprozip
    - We reuse their concept of multiple replay-targets, but we provide an unprivileged native replay target, and our container images do not depend on Docker or the internet.
  - rr
  - CDE
  - SciUnits

# Future work

- Use zpoline or SABRe to reduce caveats
- Evaluate for multi-node HPC codes
