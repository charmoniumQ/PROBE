---
from: markdown
verbosity: INFO
citeproc: yes
ccite-method: citeproc
bibliography:
  - ../zotero.bib
link-citations: yes
link-bibliography: yes
notes-after-punctuation: yes
title: Provenance tracing unmodified binaries in unprivileged mode with low overhead
author:
  - name: Samuel Grayson
    orcid: 0000-0001-5411-356X
    email: grayson5@illinois.edu
    affiliation:
      institution: University of Illinois Urbana-Champaign
      department:
        - Dept. of Computer Science
      streetaddress: 201 North Goodwin Avenue MC 258
      city: Urbana
      state: IL
      country: USA
      postcode: 61801-2302
  - name: Shofiya Bootwala
    email: shofiyabootwala@gmail.com
    orcid: 0009-0004-1871-7357
    affiliation:
      institution: Gujarat Technological University
      # department:
      #   - 
      #streetaddress: 100 Street
      city: Ahmedabad
      state: Gujarat
      country: India
      postcode: 382424
  - name: Jenna Fligor
    #orcid: 0000-0001-5411-356X
    email: jenna@fligor.net
    affiliation:
      institution: University of Illinois Urbana-Champaign
      department:
        - Dept. of Computer Science
      streetaddress: 201 North Goodwin Avenue MC 258
      city: Urbana
      state: IL
      country: USA
      postcode: 61801-2302
  - name: Kyrillos Ishak
    orcid: 0009-0003-0627-1901
    email: kyrillos.said@stud.tu-darmstadt.de
    affiliation:
      institution: Alexandria University
      #department:
      #  - Dept.
      #streetaddress: 100 Street
      city: Alexandria
      state: State
      country: Egypt
      #postcode: 1000-100
  - name: Saleha Muzammil
    #orcid: XXXX-XXXX-XXXX-XXXX
    email: l201192@lhr.nu.edu.pk
    affiliation:
      institution: National University of Computer and Emerging Sciences 
      #department:
      #  - Dept. of Computer Science
      streetaddress:  100 Street
      city: Lahore
      state: Punjab
      country: Pakistan
      #postcode: 61801-2302
  - name: Asif Zubayer Palak
    orcid: 0009-0007-9519-3317
    email: asif.zubayer.palak@g.bracu.ac.bd
    affiliation:
      institution: BRAC University
      #department:
      #  - Dept. of Computer Science
      #streetaddress:  100 Street
      city: Merul Badda
      state: Dhaka
      country: Bangladesh
      #postcode: 61801-2302
  - name: Reed Milewicz
    orcid: 0000-0002-1701-0008
    email: rmilewi@sandia.gov
    affiliation:
      department:
        - Software Eng. and Research Dept.
      institution: Sandia National Laboratories
      city: Albuquerque
      state: NM
      country: USA
      postcode: 87123
      streetaddress: 1515 Eubank Blvd SE
  - name: Daniel S. Katz
    orcid: 0000-0001-5934-7525
    email: d.katz@ieee.edu
    affiliation:
      institution: University of Illinois Urbana-Champaign
      department:
        - NCSA & CS & ECE & iSchool
      streetaddress:  1205 W Clark St
      city: Urbana
      state: IL
      country: USA
      postcode: 61801
  - name: Darko Marinov
    orcid: 0000-0001-5023-3492
    email: marinov@illinois.edu
    affiliation:
      institution: University of Illinois Urbana-Champaign
      department:
        - Dept. of Computer Science
      streetaddress: 201 North Goodwin Avenue MC 258
      city: Urbana
      state: IL
      country: USA
      postcode: 61801-2302
classoption:
  - sigconf
  - screen=true
  - review=true
  - authordraft=false
  - timestamp=false
  - balance=false
  - pbalance=true
  - anonymous=true
  - nonacm=true
papersize: letter
pagestyle: plain
lang: en-US
anonymous: yes
standalone: yes # setting to yes calls \maketitle
number-sections: yes
indent: no
date: 2024-12-15
pagestyle: plain
papersize: letter
abstract_only: no
abstract: |
  System-level provenance tracing is the idea of automatically capturing how computational artifacts came to be, including what process created each file.
  Provenance fills an important role in computational science, providing data for reproducibility, incremental computation, and debugging.
  Prior work proposes recompiling with instrumentation, using ptrace, or configuring kernel-based auditing, which at best achieves two out of three desirable properties: accepting unmodified binaries, running in unprivilege mode, and incurring low overhead.

  We present PROBE, a system-level provenance tracer that uses library interposition to achieve all three.
  We evaluate the performance of PROBE on system microbenchmarks and scientific applications.
  PROBE has a less than 10% overhead on real-world scientific applications compared to 20% with the best prior, unprivileged provenance tracers for unmodified binaries.
---

<!-- TODO: Update numbers in abstract -->

# Introduction {#sec:intro}

<!--
TODO: uniformly use "trace" instead of "track" and "collect", "interposition" instead of "interpositioning"
-->

For computational artifacts, computational provenance (henceforth **provenance**) refers to the process which generated the artifact, the inputs to that process, and the provenance of those inputs.
This definition permits a graph representation where the artifacts and processes become nodes; an edge indicates that an artifact was generated by a process or that a process used some artifact (for example, @Fig:example).

<!--
TODO:

- embed the graphviz in this file
- size text in the SVG without raw LaTeX
-->

\begin{figure}
\centering
\texttt{
\includesvg[width=0.32\textwidth,height=\textheight,pretex=\relscale{0.7}]{./prov_example.svg}
}
\caption{Example provenance graph of \texttt{fig1.png}. Artifacts are ovals; processes are rectangles.}
\label{fig:example}
\end{figure}

Provenance data has many applications including: **reproducibility**, documenting the processes needed to recompute a particular artifact, **comprehension**, visualizing how data flows in a pile-of-scripts, and **differential debugging**, determining how the process behind two computational outputs differ.

The reproducibility use-case is especially compelling due to the reproducibility crisis in computational science [@milkowskiReplicabilityReproducibilityReplication2018; @hocquetEpistemicIssuesComputational2021; @graysonAutomaticReproductionWorkflows2023].
There are other approaches for improving reproducibility such as virtualized environments, package managers, and workflows, but these all involve tedious participation from the user.
If a system can track provenance automatically, the user need only install or turn on this feature, continue their computational science experiments, and the system would keep track of how to reproduce each artifact _automatically_.

One barrier to adoption is the significant performance overhead imposed by collecting provenance data.
User-level tracing involves asking the kernel to switch over every time the program being traced (henceforth, **tracee**) does a specific kind of action.
However, context switching imposes a significant overhead.

Prior provenance tracers avoid the overhead of context switching in two ways: by embedding themselves in the kernel or by embedding themselves in user code.
Embedding in the kernel is problematic because it increases the attack surface, it is difficult to maintain, and many computational scientists will not have root-level access to the shared machines they operate on.
Embedding in user code could happen at compile-time, but that involves the added burden of recompiling all user code, including code that the user may not have compiled at all originally in the first place (due to binary package managers).
Embedding could happen through binary rewriting, on the other hand, is difficult because the syscall instructions are smaller than the necessary instructions to facilitate a function call in x86 [@yasukataZpolineSystemCall2023].
Another solution for could be to embed provenance tracing in library code at load-time by library interposition.
This technique requires neither root-level access, recompiling user code, nor extra context-switching on every event.

Prior work on provenance tracing argues that library interposition is too incomplete, difficult, or fragile for their use-case (see [@sec:discussion]).
We offer a counter-argument in the form of an implementation of a provenance tracer based on library interposition.

The contributions of this work are:

- a delineation of desirable properties of provenance tracers
- an implementation of a provenance tracer based on library interposition called [PROBE]{.smallcaps}: **P**rovenance for **R**eproducibility **OB**servation **E**ngine 
- a suite of applications that consume its provenance, demonstrating the practical utility of provenance recorded in PROBE
- theoretical and empirical evaluation of the performance, completeness, and fragility of selected provenance tracers

The rest of the work proceeds as follows:

@Sec:background defines kinds of provenance tracers, properties thereof, and use-cases thereof.
@Sec:prior-work enumerates prior provenance tracers and discusses their properties.
@Sec:design documents the design of PROBE and its related applications.
@Sec:use-cases discusses how provenance data can be used for real-world benefit and the applications we developed for PROBE.
@Sec:evaluation presents an theoretical and empirical evaluation of selected provenance tracers.
@Sec:discussion is a general discussion of the evaluation results in the context of prior work.
@Sec:future-work discusses directions for future research with PROBE.
@Sec:soundness discusses the formal semantics of the terms used in PROBE and discusses its soundness as a system.

# Background {#sec:background}

Provenance can be collected at several different levels [@freireProvenanceComputationalTasks2008], which generally trade off less semantic value for higher generality or vice versa [@herschelSurveyProvenanceWhat2017].

<!-- TODO: write about service-level -->
**Application-level** provenance the most semantically rich but least general, as it only enables collection by that particular modified application.
**Language/workflow-level provenance** is less semantically rich but more general, as it enables provenance collection in any workflow or program written for that modified workflow engine or programming language.
**System-level provenance** is the least semantically aware because it does not even know dataflow, just a history of inputs and outputs, but it is the most general, because it supports any process (including any application or workflow engine) that uses watchable I/O operations.

Operating system-level provenance tracing (henceforth **SLP**) is the most widely applicable form of provenance tracing; install an SLP, and all unmodified applications, programming languages, and workflow engines will be traced.
This work focuses on system-level provenance (SLP).

Provenance has a number of use-cases discussed in prior work:

- **Reproducibility** [@chirigatiReproZipComputationalReproducibility2016] (manual or automatic).
   Provenance tracing aids manual reproducibility because it documents what commands were run to generate the particular artifact.
   While this can also be accomplished by documentation or making the structure of the code "obvious", in practice we accept it as an axiom that there are many cases where the authors don't have enough documentation or obvious structure to easily understand how to reproduce the artifact.

   Provenance could aid in _automatic_ reproducibility, automatically replaying the processes with their recorded inputs,  or _manual_ reproducibility, showing the user the commands that were used and letting them decide how to reproduce those commands in their environment.

- **Comprehension** [@muniswamy-reddyProvenanceAwareStorageSystems2006].
   Provenance helps the user understand the flow of data in a complex set of processes, perhaps separately invoked.
   A tool that consumes provenance can answer queries like: "Does this output depend on FERPA-protected data (i.e., data located `/path/to/ferpa`)?".

- **Differential debugging** [@muniswamy-reddyProvenanceAwareStorageSystems2006].
   Given two outputs from two executions of similar processes with different versions of data and code or different systems, what is the earliest point that intermediate data from the processes diverges from each other?

- **Incremental computation** [@vahdatTransparentResultCaching1998].
   Iterative development cycles from developing code, executing it, and changing the code.
   Make and workflow engines require user to specify a dependency graph (prospective provenance) by hand, which is often unsound in practice; i.e., the user may miss some dependencies and therefore types `make clean`.
   A tool could correctly determine which commands need to be re-executed based on SLP without needing the user to specify anything.

- **Intrusion-detection and forensics** [@muniswamy-reddyProvenanceAwareStorageSystems2006]
   Provenance-aware systems track all operations done to modify the system, providing a record of how an intruder entered a system and what they modified once they were in.
   Setting alerts when certain modifications are observed in provenance forms the basis of intrusion detection.

The first four are applicable in the domain of computational science while the last is in security.
This work focuses on provenance tracers for computational science.

We define the following "theoretical" properties of provenance tracers.
They are theoretical in the sense that one does not need to do any experiments to determine these properties; only study their methods and perhaps their code.
They are enumerated in a feature matrix in \Cref{tbl:feature-matrix}.

- **Runs in user-space**:
  SLP should run in user-space as opposed to kernel-space.
  Kernel modifications increase the attack surface and is more difficult to maintain than user-space code.

- **No privilege required**:
  A user should be able to use SLP to trace their own processes without accessing higher privileges than normal every time.
  Two motivations for this property are that code running in privileged mode increases the attack surface and presents a barrier to use for non-privileged users.
  Computational scientists would likely not have root-level access on shared systems and thus may not be able to use SLPs that require privilege to run.
  We do not distinguish between privileges required to install versus privileges required to run, since they are equivalent by setuid.

- **Ability to run unmodified binaries**:
  Users should not have to change or recompile their code to track provenance.

- **Not bypassable**:
  A tracee should not be able to read data in a way that will bypass detection by the provenance tracer.

<!-- - **Coverage of many information sources**: -->
<!--   Tracing should cover many sources of informatiion, and record whether a process accessed these sources. -->
<!--   For example, access to the file system, user input, network accesses, time of day should be recorded. -->
<!--   Tracing these dependencies improves reproducibility, because we would know the non-deterministic inputs, comprehension, differential debugging, and other applications of provenance. -->

- **Records data and metadata**:
  SLP tracers always record the metadata, e.g., which file was accessed.
  Some also record the data in the file that was accessed, at the cost of higher overhead.
  One could encompass the advantages of both groups by offering a runtime option to switch between faster/metadata-only or slower/metadata-and-data.

- **Replayable**:
  The SLP tool should export an archive that can be replayed.
  The replay may be mediated by the SLP tool itself or by an external tool, e.g. Docker, VirtualBox, QEMU.
  Recording data and metadata is required for replay.

- **Replay supports deviations**:
  The replay supports executing a different code path in the reconstructed environment, so long as the different code path does not access any files outside of those the original code path accessed (those are already in the reconstructed environment).
  For example, replay the recorded execution but replace one command-line flag, environment variable, or input file.

- **Constructs provenance graph**:
  The SLP tool should construct and export a graph representation of the provenance from the observed log of provenance events.
  Certain use-cases such as incremental computation, comprehension, differential debugging, and others require the graph representation while merely replaying does not.
  Constructing the graph from a log of events is difficult due to concurrency in the system.

<!-- Empirical properties include the following. -->
<!-- We expect the empirical properties to vary widely depending on the tracee, so one would need to evaluate these properties on a suite of benchmarks that are representative of the intended use-case. -->

<!-- - **Performance overhead on tracee**: -->
<!--   SLP should have a minimal performance overhead from native execution. -->
<!--   If the performance overhead is noticeable, users may selectively turn it off, resulting in provenance with gaps in the history. -->
  
<!-- - **Occurrences of bypass in tracee**: -->
<!--   The circumstances by which I/O operations can bypass detection can be evaluated theoretically, empirical study can determine how often those circumstances occur in the tracee. -->



<!--
TODO: Discuss reproducibility options
-->

# Prior work {#sec:prior-work}

There have been several methods of tracing SLP proposed in prior work:

<!-- TODO:
- List every prior work for each method
- Cite numbers for performance
- Check on that our claims on the other constraints are correct
-->

- **Virtual machines**: running the tracee in a virtual machine that tracks information flow.
  This method is extremely slow; e.g., PANORAMA has 20x overhead [@yinPanoramaCapturingSystemwide2007].

- **Recompiling with instrumentation**: recompile, where the compiler or libraries insert instructions that log provenance data, e.g., [@maMPIMultiplePerspective2017].
  This method does not work with unmodified binaries.

- **Static/dynamic binary instrumentation**: either before run-time (static) or while a binary is running (dynamic) change the binary to emit provenance data [@leeHighAccuracyAttack2017].
  These methods requires special hardware (e.g., Intel CPU), a proprietary tool (e.g., Intel PIN), and often root-level access (as Intel PIN does).

- **Kernel modification**: modify the kernel directly or load a kernel module that traces provenance information, e.g., [@pasquierPracticalWholesystemProvenance2017].
  This method is not in user-space.

- **Use kernel auditing frameworks**: use auditing frameworks already built in to the kernel (e.g., Linux/eBPF, Linux/auditd, Windows/ETW).
  This method is not unprivileged.

- **User-level debug tracing**: use user-level debug tracing functionality provided by the OS (e.g, Linux/ptrace used by `strace`, CDE [@guoCDEUsingSystem2011], Sciunit [@phamUsingProvenanceRepeatability2013], Reprozip [@chirigatiReproZipComputationalReproducibility2016], RR [@ocallahanEngineeringRecordReplay2017]).

- **Library interposition**: replace a standard library with an instrumented library that emits provenance data as appropriate.
  This could use the `LD_PRELOAD` of Linux and `DYLD_INSERT_LIBRARIES` on MacOS.

<!-- TODO: Address completeness -->

If unprivileged execution, unmodified binaries, and low performance overhead are hard-requirements, the only possible methods are user-level debug tracing and library interposition.

Using the results of a recent literature survey [@graysonBenchmarkSuitePerformance2024], we identify the user-level tracing provenance collectors: PTU [@phamUsingProvenanceRepeatability2013], Sciunit [@tonthatSciunitsReusableResearch2017], and ReproZip [@chirigatiReproZipComputationalReproducibility2016].
We did not identify any feasible library interposition provenance collectors.
OPUS [@balakrishnanOPUSLightweightSystem2013] is one example, but we were not able to replicate it.
It was last developed almost a decade ago, and it uses end-of-life Python 2.7 and Java 1.6.

We also selected the following record/replay tools, which do not claim to be provenance tracers, but involve tracing provenance events with user-level tracing: RR [@ocallahanEngineeringRecordReplay2017], CDE [@guoCDEUsingSystem2011] and CARE [@janinCAREComprehensiveArchiver2014].
If they are performant enough, perhaps they could be converted to provenance tracers.

Lastly, we selected `strace`.
`strace` merely logs the events but does not do any processing on the events (e.g., constructing a provenance graph).
Therefore, `strace` is close to the theoretical minimal overhead for bare user-level debug tracing.

We examine the properties of these in @Tbl:feature-matrix.

\begin{table*}
\centering
\footnotesize
\input{feature_matrix.tex}
\caption{Feature matrix of provenance collectors and the properties described above. See \Cref{sec:background} for explanation of the properties.}
\label{tbl:feature-matrix}
\end{table*}

In user-level debug tracing, the tracer runs in a separate process than the tracee.
Every time the tracee does a system call, control switches from the tracee to the kernel to the tracer and back and back [@Fig:sequence].
This path incurs two context switches for every system call.

O'Callahan et al. mitigate this by "inject[ing] into the recorded process a library that intercepts common system calls, performs the system call without triggering a ptrace trap, and records the results to a dedicated buffer shared with RR [the tracer program]" [@ocallahanEngineeringRecordReplay2017].
However, there are some system calls that RR cannot handle solely in the tracee's code, and those system calls will still cause two context switches.

On the other hand, in library interposition, the tracer code is part of a library dynamically loaded into the tracee's memory space.
While this imposes restrictions on the tracer code, it obviates context switching on every provenance event [@Fig:sequence].

\begin{figure}
\centering
\includesvg[width=0.3\textwidth,pretex=\relscale{0.9}]{./ptrace.svg}

\hspace{10mm}

\includesvg[width=0.3\textwidth,pretex=\relscale{0.9}]{./lib_interpose.svg}
\caption{Sequence diagram of process with user-level debug tracing (top) and library interposition (bottom).}
\label{fig:sequence}
\end{figure}

<!--
TODO:
Prior surveys/SoK
- Freire et al. Provenance for Computational Tasks: A Survey
- Oliveira et al. Provenance Analytics for Workflow-Based Computational Experiments: A Survey
- SoK by Inam et al. https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=10179405
- Pimentel et al. A Survey on Collecting, Managing, and Analyzing Provenance from Scripts
- our prior 2024 ACM REP work

--> 

# Design {#sec:design}

Even the most feature complete provenance tracers in @Tbl:feature-matrix use user-level debug tracing which can have a large overhead.
Therefore, we set out to build a provenance tracer that offers similar features to the others in [@Tbl:feature-matrix] but uses library interposition for evaluation in @Sec:evaluation.

Our provenance tracer is called [PROBE]{.smallcaps}: **P**rovenance for **R**eplay **OB**servation **E**ngine.
PROBE has a recording phase, a transcription phase, and an exporting phase.

Users can **record** any shell command by writing `probe record` in front of the shell command.
In the recording phase, PROBE will set `LD_PRELOAD` to load `libprobe.so` ahead of the systems usual C library and run the user's provided command

The core of PROBE is a library interposer for libc, called `libprobe.so`.
`libprobe.so` exports wrappers for I/O functions like `open(...)`.
The wrappers:

1. log the call with arguments
3. record the state of the system (e.g., during `open(..., O_RDWR)`, PROBE will make a copy of the file target)
2. forward the call to the _true_ libc implementation
3. log the underlying libc's returned value
4. return the underlying libc's returned value

There is no data shared between threads as the log is thread-local.
To make logging as fast as possible, the log is a memory-mapped file.
If the logged data exceeds the free-space left in the file, `libprobe.so` will allocate a new file big enough for the allocation.

The **transcription phase** is run after the user's command terminates.
In the transcription phase, PROBE combines the logged data into a single object that can be inserted into the provenance store or copied as a file to another host.

The PROBE log is conceptually a list of processes, where each process has a list of threads, and each thread has an ordered list of provenance events.
An event may be reading a file, forking another process, executing a new process (`exec` syscall), or waiting on a process.
By carefully analyzing the log of events, PROBE can construct a dataflow graph for the system.
The semantics of events and their conversion to a graph is described more thoroughly in @Sec:soundness.
The dataflow can be inserted in the user's system-wide provenance store, allowing PROBE to track provenance of objects involved in multiple recordings.

In the **exporting phase**, PROBE or another program analyzes the provenance graph from the provenance store and produces some result or artifact.

The **provenance store** is implemented as a pair of SQLite tables: one table containing metadata regarding a file-version and another containing metadata regarding processes.
Each process in the **process table** is associated with zero or one _parent processes_.
The graph whose nodes are processes and edges point to the parent process is a tree.

Each file-version in the **file-version table** is associated with inodes (many-to-one) but zero or more paths due to symlinks and hardlinks.
The assocation from file-version to inode is not invertible, since one multiple versions of one inode may have been observed.
Each file-version is also associated with exactly one _creating process_, and zero or more _reading processes_, i.e., processes that are known to read the file.
The dataflow graph is simply the graph whose nodes are processes and files and whose edges show creation or reading (see @Sec:soundness).
By its nature, it is acyclic and bipartite.

Finally, we developed wrapper programs for **`scp`** and **`ssh`**.
One may want to run processes on remote hosts, usually because the remote has more computational resources or is "closer" to the data.
Such an operation would usually be a boundary past which provenance cannot be tracked.
However, we worked around this problem by deploying executables on the `$PATH` called `ssh` and `scp` ahead of the true `ssh` and `scp`.
Our programs examine the arguments and wrap the true `ssh` and `scp` in a _provenance aware_ manner.

- For `ssh`, we send a copy of PROBE to the remote, if it does not already have one, run the user's command in a shell with PROBE recording turned on, and insert the provenance collected on the remote to the provenance store.

- For `scp`, we send or receive the files as expected, but we also attempt to send or receive the provenance associated with those files from the remote's provenance store.

<!--
TODO: Read "Tracking and Sketching Distributed Data Provenance Tanu Malik"
-->
 

# Applications of provenance data {#sec:use-cases}

We developed applications that consume PROBE provenance to:

1. demonstrate PROBE collects "enough" provenance data for practical uses
2. motivate pervasive use of provenance tracing (on by default), which in turn motivates minimizing the overhead

Our applications include:

<!-- 1. Visualizing the dataflow graph -->
1. Automatic Makefile or workflow conversion
2. Exporting a OCI or Docker container for re-execution

<!--
## Visual representations

Some users may have a complex pile of scripts or spaghetti code that is difficult to analyze statically.
If they simply run their scripts in PROBE, PROBE observes their provenance and can render it graphically.

TODO: Details on how we got this representation

TODO: Example graph
-->

## Automatic workflow conversion

A **workflow** is a directed acyclic graph^[There are some exceptions where the graph may be cyclic. TODO] where each node represents a program and each edge is a data item, usually a file.
Workflow systems like Galaxy [@thegalaxycommunityGalaxyPlatformAccessible2024], Snakemake [@kosterSnakemakeScalableBioinformatics2012], and Nextflow [@ditommasoNextflowEnablesReproducible2017] are commonly used in domains such as bioinformatics, machine learning, and data science.
Workflows are advantageous because:

- It may be easier for non-experts than Python
- Workflow languages are specialized for gluing together existing components
- The workflow structure exposes parallelism, and many engines support distributed computing
- Many workflow engines implement incremental computation, so if one node changes, only the downstream artifacts need to be recomputed

However, it can be challenging to migrate from an _ad hoc_ process or a pile of scripts to a structured workflow.

PROBE solves this problem by converting an _ad hoc_ process to a structured workflow automatically.
Users need only execute their process once by hand in PROBE, which captures the provenance.
Then the user asks PROBE to export a workflow that will contain the commands used to write a particular output.
PROBE supports generating Nextflow and Makefile workflows.
Now, users can more easily switch to workflows and gain the benefits noted above.

## Exporting a container

Containers are useful for automatically distributing a software environment.
However, sometimes important code environments are not containerized.
Therefore, containerization must be a non-trivial amount of work that some users, especially non-experts, do not have time for.

PROBE reduces the barrier to export containers by automatically containerizing the software environment.
One simply runs their code in PROBE.
PROBE collects the provenance of their process.
We reconstruct a minimal, portable OCI image based on a provenance log.
These files are then transferred into a new container's filesystem, and the container's configuration is set to replicate the original process's command, environment, and working directory.
Finally, the container image is committed and optionally pushed to the Docker daemon for immediate use.

``` sh
$ probe record ./run_script.sh
hello world

$ probe export docker-image my-image:1.0.0

$ docker run my-image:1.0.0
hello world
```

<!-- We tackled several key technical challenges in the transformation process: -->

<!-- 1. We developed methods to capture inline commands that modify files, integrating these operations seamlessly into unified workflow processes. This approach minimized intermediate steps while maintaining execution logic fidelity. -->
<!-- 2. We refined the handling of sequential command chains, representing complex sequences as cohesive workflow processes, thereby reducing redundancy and improving clarity. -->
<!-- 3. We resolved challenges related to chained commands with dependencies, ensuring accurate preservation of execution order and context, particularly in scenarios involving overlapping inputs and outputs. -->

<!-- Our contributions have significantly enhanced PROBE's capability to generate workflows from provenance data. -->
<!-- The transformation of arbitrary command sequences into structured Nextflow pipelines enables researchers to achieve reproducibility without modifying their exploratory workflows. -->
<!-- The resulting workflows demonstrate both executability and portability, facilitating sharing, modification, and scaling across computational environments. -->
<!-- Furthermore, our implementation preserves crucial provenance information, including input-output relationships and intermediate states, integrating them seamlessly into the workflow structure. -->
<!-- This advancement aligns with broader objectives in workflow automation across research and industry domains, where reproducibility and scalability remain paramount concerns. -->
<!-- By integrating these capabilities into PROBE, our work enables users to transform ephemeral command executions into durable, reproducible artifacts, contributing to more robust and reliable computational research practices. -->


# Empirical evaluation {#sec:evaluation}

We collected the benchmarks used in prior work in [@Tbl:prior-benchmarks].
We could not find publications discussing the recording performance of ReproZip or CDE.
Regarding CDE, Guo and Engler state "We have heard that ptrace interposition [the method used by CDE] can cause slowdowns of 10X or more, but we have not yet performed a rigorous performance stress test" [@guoCDEUsingSystem2011].
Between the publications which do contain benchmarks, there is no overlap.

\begin{table}
\centering
\begin{tabular}{llp{1.8in}}
\toprule
Prov tracer                                        & Gmean              & Benchmarks used for recording                  \\
\midrule
RR \cite{ocallahanEngineeringRecordReplay2017}     & 1.58               & cp, compile, JavaScript, Firefox, Samba server \\
PTU \cite{phamUsingProvenanceRepeatability2013}    & 1.25               & geospatial task, natural language task         \\
Sciunit \cite{tonthatSciunitsReusableResearch2017} & 1.37               & hydrology task, data science task              \\
\end{tabular}
\caption{Benchmarks used in publications on selected provenance tracers.}
\label{tbl:prior-benchmarks}
\end{table}

<!--
RR (1.5 * 1.75 * 1.5 * 1.6)**(1/4)
PTU (1.35 * 1.15)**(1/2)
Sciunit (81/80 * 1.0 * 1.0 * 466/240 * 848/464 * 1017/551)**(1/6)
-->

Grayson et al. give a representative benchmark suite based on benchmarks used in other provenance works including [@graysonBenchmarkSuitePerformance2024]:

- BLAST (multiomics search application) [@altschulBasicLocalAlignment1990] with a predefined set of queries [@coulourisBlastBenchmark2016]
- Apache under synthetic load
- lmbench (synthetic benchmark for I/O bandwidth and latency) [@mcvoyLmbenchPortableTools1996]
- Postmark (synthetic benchmark for small file I/O) [@katcherPostMarkNewFile2005]
- SPLASH-3 CPU benchmarks [@sakalisSplash3ProperlySynchronized2016]
<!-- - Shell utilities in a tight loop -->

The performance of provenance tracing depends greatly on the ratio of provenance operations to other operations.
This ratio is a property of the application, not the system, and cannot be estimated from synthetic benchmarks.
The only way to determine that ratio is to test real-world applications.
BLAST and SPLASH-3 is the only real-world application in the Grayson benchmark suite, so we added the following:

- A data science Jupyter notebooks from Kaggle.com. This notebooks read some data, create plots, and output a predicted dataset.
<!-- - 2 projects from Astrophysics Source Code Library [@allenAstrophysicsSourceCode2012], sorted by citations on OpenCitations [@peroniOpenCitationsInfrastructureOrganization2020]. From this set, we chose Quantum Espresso (calculates electronic structure) and Astropy (generic toolbox for astronomical computations). -->
- 2 projects from the Journal of Open Source Software, sorted by citations on OpenCitations [@peroniOpenCitationsInfrastructureOrganization2020]. From this set, we chose UMAP manifold leraning example (data sci.) and hdbscan clustering example (data sci.).
<!-- - Projects from NixOS Quantum Chemistry repository [@kowalewskiSustainablePackagingQuantum2022]. We chose Bagel (electronic structure code) from this set. -->

Regarding selected provenance tracers:
- we wanted to test RR, but it requires root to install, so it does not fit our selection criteria^[RR requires the kernel configuration variable `perf_event_paranoid` to be set to a number less than `2`. On some systems, this may already be set, but on the ones we were testing (default Ubuntu 22.04), it is not.].
- For `strace`, we filtered logging to record only those syscalls relevant for provenance to make a fair comparison between with PROBE.
- We excluded out CDE since Provenance To Use is a close modification of CDE; adding CDE did not add much more information.
- We excluded Sciunit since Sciunit internally uses Provenance To Use, but adds block-based deduplication; if Provenance To Use is slow, then Sciunit will be slower.
- We included two configurations of PROBE: one that copies file data (necessary for automatic, containerized replay) and another which only captures metadata.

We run 5 trials of each benchmark and provenance tracer.
For each provenance tracer and workload, we infer a log-normal distribution from every trial.
We use the log-normal instead of normal distribution for three reasons:

- **Positive skew**:
  The right tail (slower than expected) is heavier than the left tail (faster than expected).
  Real-world runtime data [@mytkowiczProducingWrongData2009; @suhEMPExecutionTime2017] tends to exhibit positive skew.
  
- **Positive-support**:
  Normal distributions give a non-zero probability density to negative runtimes, which are not physically possible.
  Log-normal only gives non-zero probability to positive runtimes.

- **Ease of ratio distribution**:
  We will compute the distribution of the _overhead ratio_ between provenance tracers and native execution of the same application.
  The ratio of two normally distributed variables is a very complex distribution (see Eqn. 1 in [@hinkleyRatioTwoCorrelated1969]).
  Contrarily, the ratio of two log-normal variables is itself log-normal.

We infer the log-normal distribution using unbiased maximum-liklihood estimators (this is similar but less biased than the geometric mean).
Lastly, we compute the distribution of the overhead ratio of each provenance tracer, presenting its expected value and standard deviation in the tables below [@Tbl:walltime].

<!--
We timed benchmarks to verify that none of them finish in faster than 1 seconds, so the execution time is not dominated by program loading.

Ensured application benchmarks are not too fast, but they were much longer

Too slow would be too few data

Loop more so we can say 3 seconds instead
-->

\begin{table*}
\footnotesize
\input{data_walltime.tex}
\normalsize
\caption{Expected value of walltime overhead of applications in various provenance tracers over native execution. A value of "50\%" means that running the program in the provenance tracer takes 1.5x as long when running natively. There may be negatives numbers due to the random variation in trials; in those cases, look at the standard deviation.}
\label{tbl:walltime}
\end{table*}

While it may be tempting to average the columns of the table, the average would not be meaningful, because that average would depend heavily on the choice of benchmarks, how many I/O heavy benchmarks are included, etc.
Instead focus on the workload grouping (first column).
While both configurations of PROBE can experience grater overhead in the synthetic benchmarks (syscall and synth. file I/O) than their competitors, in the real-wold applications (data sci. and multi-omics) both configurations of PROBE fare much better than their competitors.
Note that the first two columns compare metadata-only provenance tracers while the latter three columns compare metadata-\&-data provenance tracers.

<!-- Instead, we show the average within each group of related programs. -->
<!-- To summarize the performance difference, we use the Friedman test. -->
<!-- The Friedman test operates on a matrix of ranks, for each workload, which provenance tracer had 1st place, 2nd place, etc., which is robust to heteroscedasticity [@Fig:ranks]. -->

<!-- \begin{figure*}[h] -->
<!-- \centering -->
<!-- \includesvg[width=0.9\textwidth]{./ranks_walltime.svg} -->
<!-- \caption{Confidence intervals of post-hoc Nemenyi test. The number line shows where each provenance tracer's average rank (1st, 2nd, etc.) over all workloads. A black horizontal bar connects the ranks which have overlapping confidence intervals.} -->
<!-- \label{fig:ranks} -->
<!-- \end{figure*} -->

<!-- While PROBE performs significantly better than the other provenance tracers (PTU and CARE), the difference is not statistically significant. -->

# Discussion {#sec:discussion}

Prior works [@ocallahanEngineeringRecordReplay2017; @pasquierPracticalWholesystemProvenance2017] argue that library interposition is not appropriate for SLP:

> In practice, we have found that method [dynamic linking to interpose wrapper functions] to be insufficient, due to applications making **direct system calls**, and **fragile**, due to variations in C libraries, and applications that require their own preloading [37, 3].

--- @ocallahanEngineeringRecordReplay2017, emphasis ours

**Bypassed by direct syscalls**:
While it is true that library interposition is bypassable by direct system calls, those cases are rare in practice.
Syscall numbers are different on every operating system; however, `libc` call signatures are standardized in ANSI C and, with greater specificity, in POSIX.
Source code written to call `libc` functions can be compiled on a variety of platforms.
Therefore, `libc` becomes the _de facto_ interface between application code and the host platform.

The default Ubuntu packages for Python, Java JRE, and Bash all use `libc`, so any programs written for those interpreters using the usual I/O mechanisms will not bypass library interposition.
The GCC, Clang, Rust, and the Glasgow Haskell Compiler packages in Ubuntu also emit code that targets `libc`.
The only major exceptions are Zig and Go lang.

One may at least detect that a potential bypass may occur, by analyzing the machine code of executables and libraries and searching for the `syscall` instruction.
PROBE is in a primary position to do this, since it already hooks all `exec` calls, however we have not had enough time to implement this yet.

**Fragility**:
Library interposition may interfere with other applications that also use library interposition.
Each interposer would intercept the call and hands it off to the next library on the path, unaware if this is a true `libc` or an interposing `libc`, like a telescoping tube.
It is possible that the behavior modifications introduced by one interposer violates some implicit contract expected by another, but it is equally possible that each passes along the call to the next without negative interference.

O'Callahan's citations refer to ASAN (Address SANitization) [@serebryanyAddressSanitizerFastAddress2012] and WINE (Wine Is Not an Emulator) [@amstadtWineNotEmulator].
We tested ASAN in PROBE.
ASAN has to be informed to ignore that it is not at the _top_ of the preload list by setting the environment variable `ASAN_OPTIONS=verify_asan_link_order=0`.
After that, no errors occurred.

> An argument in favour of such [interposition] systems is that modifications to existing libraries are more likely to be adopted than modifications to the kernel. However, for this approach to work, all applications in the system need to be built against, or dynamically linked to, provenance-aware libraries, replacing existing libraries.

--- @pasquierPracticalWholesystemProvenance2017

**Recompiling binaries**:
This is only true for _compile-time_ linkage of library interposition.
However, modern operating systems (Linux, \*BSD, MacOS, Windows) provide for linking libraries at program load-time.
PROBE does not require recompilation or re-linking of binaries.

<!--
- Compare theoretically and empirically with others
  - Library interposition trades off in completeness slightly.
    - We can detect and caution the user when they are tracing an application for which PROBE provenance collection may be incomplete
- Collecting provenance by itself is not the end goal; can PROBE provenance do some of the motivating applications mentioned above?

- **RQ:** How does the provenance output of PROBE compare with prior provenance tracers (case studies)? Is it more complete or detailed?
  - Consider system-level provenance tracers separately from workflow-level and language-level provenance tracers
  - Cases: pile-of-scripts, standalone workflow, embedded workflow, C application, Python application, Jupyter Notebook
- **RQ:** How faithfully can heuristics create a runnable package specification from a prov description?
-->

# Future work {#sec:future-work}

Future work should do more comparisons and evaluations of state-of-the-art provenance tracers.
Besides recording time, future work should investigate replay time.
Not just measuring performance, future work should seek to _model_ performance theoretically.
What factors influence the performance of provenance recording?
Future work should also investigate the fidelity of said replay.
For what proportion of real-world programs is the provenance tracer able to record/replay bit-wise equivalent results?

Aside from performance, future work should investigate applications for provenance data.
Perhaps the adoption of provenance tracers in practice could be furthered by working with scientists to do user studies.
It is difficult to predict the full details of problems when applying research into practice [@besseyFewBillionLines2010].

<!-- - This Docker _image_ should not be confused with a `Dockerfile`. -->
<!--   A `Dockerfile` is much smaller and more convenient to send, but it does not necessarily build to a bit-wise reproducible Docker image. -->

<!-- - Improve completeness: static binary rewriting -->
<!-- - Improve performance -->
<!-- - Multi-node and HPC cases -->

# Conclusion {#sec:conclusion}

We present PROBE, a provenance tracer for unmodified binaries running in unprivileged mode with low overhead.
While the initial evaluation of PROBE is promising, our ultimate position is not on PROBE but on library interposition.
Despite prior work dismissing library interposition for provenance tracing [@Sec:discussion], but we show that library interposition is possible, has few of the putative downsides, and is much faster than its alternatives.

\section*{Acknowledgments}

This work was partially supported by Sandia National Laboratories.

\section*{Availability}

1. Install Nix with flakes. This can be done on any Linux (including Ubuntu, RedHat, Arch Linux, not just NixOS), MacOS X, or even Windows Subsystem for Linux.

   - If you don't already have Nix on your system, use the [Determinate Systems installer](https://install.determinate.systems/).

   - If you already have Nix (but not NixOS), enable flakes by adding the following line to `~/.config/nix/nix.conf` or `/etc/nix/nix.conf`:

     \small

     ```
     experimental-features = nix-command flakes
     ```

     \normalsize

   - If you already have Nix and are running NixOS, enable flakes with by adding `nix.settings.experimental-features = [ "nix-command" "flakes" ];` to your configuration.

2. Acquire the source code from an anonymized repository:

   \small

   ``` sh
   mkdir PROBE
   cd PROBE
   curl --output PROBE.zip \
     https://anonymous.4open.science/api/repo/PROBE/zip
   unzip PROBE.zip
   rm PROBE.zip
   ```
   
   \normalsize

3. Build PROBE (takes about 20 minutes if building from scratch)

   \small

   ```sh
   # Launches a shell with PROBE on the PATH
   nix shell .#probe-bundled
   ```
   
   \normalsize

4. In the subshell from the previous command,

   \small

   ```sh
   probe record <CMD ...>
   ```

   \normalsize

\appendix

# Semantics and soundness of PROBE {#sec:soundness}

The user supplies a **command**, such as `python script.py -n 42`, to PROBE.

PROBE runs command with certain environment variables set, resulting in a **process**.

The process may create **child processes** that will also get traced by PROBE.

If a process calls a syscall from the `exec`-family, a new process is created with the same PID. We call the pair of (PID, "number of times `exec` has been called"), an **exec epoch**. Each process has at least one exec epoch.

Each process can spawn kernel-level **threads** that provide concurrent control-flow in the same address-space identified by the triple (PID, exec epoch, TID).

Threads do **operations**, like "open `file.txt` for reading" or "spawn a new process", identified by (PID, exec epoch, TID, operation number), where operation number increments for every operation the thread does.

A **dynamic trace** of a command is an tuple of:

- a PID which is the root
- a mapping of processes to an ordered list of exec epochs
- a mapping of exec epochs to threads
- a mapping of threads to a list of operations

Dynamic traces are what PROBE actually records.

**Program order** is a partial order on operations where $A$ precedes $B$ in program order if $A$ and $B$ are in the same thread and $A$'s operation number is less than $B$'s.

**Synchronization order** is a partial order on operations where $A$ precedes $B$ in program order for specific special cases based on the semantics of the operation.
PROBE currently tracks the following cases:

- $A$ is an exec and $B$ is the first operation of the next exec epoch for that process
- $A$ is a process-spawn or thread-spawn and $B$ is the first operation in the new process or thread.
- $A$ is a process-join or thread-join and $B$ is the last operation in the joined process (any thread of that process) or joined thread.

But the model is easily extensible other kinds of synchronization including shared memory locks, semaphores, and file-locks.

**Happens-before order**, denoted $\leq$, is a partial order that is the transitive closure of the union of program order and synchronization order.

We define a **dataflow** as a directed acyclic graph whose nodes are operations or versioned files.
The edges are the union of happens-before edges and the following:

- If operation $A$ opens a file at a particular version $B$ for reading, $A \to B$.
- If operation $A$ closes a file at a particular version $B$ which was previously open for writing, $A \to B$.

Tracking the _versioned files_ instead of files guarantees non-circularity.

Rather than track every individual file operation, we will only track file opens and closes.
If processes concurrently read and write a file, the result is non-deterministic.
Most working programs avoid this kind of race.
If a program does have this race, the dataflow graph will still be sound, but it may be _imprecise_, that is, it will not have all of the edges that it could have had if PROBE tracked fine-grain file reads and writes.

A **file** is an inode.
Defining a file this way solves the problem of _aliasing_ in filesystems.
If we defined a file as a path, we would be fooled by symlinks or hardlinks.
When we observe file operations, it is little extra work to also observe the inodes corresponding to those file operations.

<!--
TODO: discuss between-process-tree and within-process-tree provenance
-->

In practice, we use the pair modification times and file size as the version.
Modification time can be manipulated by the user, either setting to the current time with `touch` (common) or resetting to an arbitrary time with `utimes` (uncommon).
Setting to the current time creates a new version which does not threaten the soundness of PROBE.
Setting to an arbitrary time and choosing a time already observed by PROBE does threaten its soundness.
For this reason, we consider the file size as a "backup distinguishing feature".
It is unlikely that a non-malicious user would accidentally reset the time to the exact time (nanosecond resolution) we already observed and have the exact same size.

In the event of a data race on a file write, the dataflow graph generated by our approach ensures that all potential dependencies are captured as edges. The child processes of a parent process inherit write access to a file opened by the parent and are treated as dependencies of the incremented final version of the file. This guarantees that no critical dependency is overlooked, ensuring the soundness of the dataflow graph. However, the approach may not achieve completeness, as some processes with write access may not represent true dependencies. Since we have limited information about the order in which the shared file is accessed by the processes and the exact change made to the file, this approach uses the access mode effectively to construct a graph that prioritizes soundness.

## Event coverage

We wrapped every function that does file I/O or changes how paths are resolved (e.g., `chdir`) in the following chapters of the GNU C Library manual^[<https://www.gnu.org/software/libc/manual/html_node/>] with the exception of redundant functions:

- Chapter 12. Input/Output on Streams
- Chapter 13. Low-Level Input/Output
- Chapter 14. File System Interface
- Chapter 15. Pipes and FIFOs
- Chapter 16. Sockets
- Chapter 26. Processes

One function, A, is redundant to another one B, if I/O through A necessitates a call through B.
We need only wrap B to discover that I/O will occur.
For example, we need only log file openings and closings, not individual file reads and writes.

Our research prototype wraps:

- file `open` and `close` family of functions^[The "family of functions" includes 64-bit variants, `f*` variants (`fopen`), re-open, close-range]
- `chdir` family of functions
- directory opens, closes, and iterations families of functions
- file `stat` and `access` families of functions
- file `chown`, `chmod`, and `utime` families of functions
- `exec` family of functions
- `fork`, `clone`, `wait` families of functions
- `pthread_create`, `pthread_join`, `thrd_create`, `thrd_join`, etc. functions

\printbibliography
