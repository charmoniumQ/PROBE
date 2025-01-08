---
# pandoc --template=../usenix_template.tex --filter=pandoc-crossref  --citeproc --biblatex -i README.md -o README.tex
# latexmk -interaction=nonstopmode -shell-escape -pdf -shell-escape -emulate-aux-dir -Werror README
# env TEXINPUTS=$(dirname $PWD)//: pdflatex -interaction=nonstopmode -shell-escape README
# biber README
from: markdown
verbosity: INFO
citeproc: yes
ccite-method: citeproc
bibliography:
  - ../zotero.bib
link-citations: yes
link-bibliography: yes
notes-after-punctuation: yes
title: Transparent, performant, non-privileged provenance tracing through library interposition
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
abstract: >
  System-level provenance tracing is the idea of automatically capturing how computational artifacts came to be (e.g., what version of the program wrote this file).
  While provenance is often discussed in the context of security, it also fills an important niche in computational science, providing data for reproducibility, incremental computation, and debugging.
  Unlike a security administrator, computational scientists do not necessarily have root-level access to the machine on which they want to trace provenance.
  Prior work proposes recompiling with instrumentation, ptrace, and kernel-based auditing, which at best achieves two out of three desirable properties: transparency, performance, and non-privilege.

  We present PROBE, a system-level provenance tracer that uses library interpositioning to achieve all three.
  We evaluate the performance of PROBE on system microbenchmarks and scientific applications.
  We also discuss the completeness of the provenance that PROBE collects compared to other provenance tracers.
---

# Introduction {#sec:intro}

<!--
TODO: introduce new style for new terms
TODO: uniformly use "trace" instead of "track" and "collect"
-->

For computational artifacts, computational provenance (just **provenance** from here on) refers to the process which generated the artifact, the inputs to that process, and the provenance of those inputs.
This definition permits a graph representation where the artifacts and processes become nodes; an edge indicates that an artifact was generated by a process or that a process used some artifact (for example, @fig:example).

<!--
TODO:
- embed the graphviz in this file
- size text in the SVG without raw LaTeX
-->

\begin{figure}
\centering
\includesvg[width=0.5\textwidth,height=\textheight,pretex=\relscale{0.8}]{./prov_example.svg}
\caption{Example provenance graph of \texttt{fig1.png}. Artifacts are ovals; processes are rectangles.}\label{fig:example}
\end{figure}

Provenance has a number of use-cases discussed in prior work:

1. **Reproducibility** [@chirigatiReproZipComputationalReproducibility2016].
   Provenance could aid in _automatic_ reproducibility, automatically replaying the processes with their recorded inputs,  or _manual_ reproducibility, showing the user the commands that were used and letting them decide how to reproduce those commands in their environment.

2. **Incremental computation** [@vahdatTransparentResultCaching1998].
   Iterative development cycles from developing code, executing it, and changing the code.
   A system like Make reads a provenance graph and determines which processes need to be re-executed.

3. **Comprehension** [@muniswamy-reddyProvenanceAwareStorageSystems2006].
   Provenance helps the user understand the flow of data in a complex set of processes, perhaps separately invoked.
   An tool that consumes provenance can answer queries like:
   
   - "Where did this data file come?" Answering, "this raw data processed by this list of commands".
   - "From what version of the script did this figure derive?" Answering with a copy of the script at the particular version which generated that output. While code is often versioned in VCS, large binary outputs like data and figures are more difficult.
   - "Does this output use FERPA-protected data (i.e., data located /path/to/ferpa)?"

4. **Differential debugging** [@muniswamy-reddyProvenanceAwareStorageSystems2006].
   Given two outputs from two executions of similar processes with different versions of data and code or different systems, what is the earliest point that intermediate data from the processes diverges from each other?

5. **Intrusion-detection and forensics** [@muniswamy-reddyProvenanceAwareStorageSystems2006]
   Provenance-aware systems track all operations done to modify the system, providing a record of how an intruder entered a system and what they modified once they were in.
   Setting alerts when certain modifications are observed in provenance forms the basis of intrusion detection.

The first four are applicable in the domain of computational science while the last is in security.
This work focuses on provenance tracers for computational science.

These features necessitate the following design features of provenance tracers:

1. **Non-privilege**:
   A user should be able to use SLRP to trace their own processes without root-level access.
   While appropriate for security use-cases, computational scientists would likely not have root-level access on shared systems.

2. **Performance**:
   SLRP should have a minimal performance overhead from native execution.
   If the performance overhead is noticeable, users may selectively turn it off, resulting in provenance with gaps in the history.

3. **Transparency**:
   Users should not have to change or recompile their code to track provenance.

Prior work misses at least one of these three:

- eBPF, Linux Audit framework, Linux Provenance Modules/Linux Security Modules [@batesTrustworthyWholeSystemProvenance2015], and CamFlow [@pasquierPracticalWholesystemProvenance2017] use Linux kernel-level functionality violating non-privilege.

- ReproZip [@chirigatiReproZipComputationalReproducibility2016] and Sciunits [@tonthatSciunitsReusableResearch2017] use ptrace, which has a significant performance overhead.
  Record/replay tools such as RR [@ocallahanEngineeringRecordReplay2017] and CDE [@guoCDEUsingSystem2011] are similar to provenance tracers in this category.
  Record/replay tools seek automatic reproducibility but do not satisfy the other features of provenance tracers discussed above.

- PASSv2 [@muniswamy-reddyLayeringProvenanceSystems2009] requires the user to instrument their code to emit provenance data to a colelctor, violating transparency.

We present a provenance tracer based on library interposition called PROBE, a non-privileged SLRP tracer that maintains performance and transparency.
The rest of the work proceeds as follows:

- @Sec:prior-work summarizes prior SLRP and related prior works
- @Sec:design documents the high-level design of PROBE.
- @Sec:implementation documents low-level implementation details of PROBE.
- @Sec:completeness-analysis quantifies the completeness of PROBE with respect to various information sources.
- @Sec:future-work outlines future work we would like to do on PROBE.
- @Sec:performance-analysis outlines how we intend to analyze the performance of PROBE and related work.

# Background {#sec:background}

Provenance can be **retrospective**, tracing computational steps that _were run_, or **prospective**, determining what computational steps _should be run_ [@zhaoApplyingVirtualData2006].
Some programming systems permit determining prospective provenance, but it is easier to trace retrospective provenance dynamically.

Provenance can be collected at several different levels

<!-- TODO: write about service-level -->
1. **Application-level**: modify each application to emit provenace data.
   Application-level provenance is the most semantically rich but least general, as it only enables collection by that particular modified application [@freireProvenanceComputationalTasks2008].

2. **Language/workflow-level provenance**: modify the programming language or workflow language, and all programs written for that language would emit provenance data.
   Workflow engines are only aware of the dataflow, not higher-level semantics, so workflow-level provenance is not as semantically rich as application-level provenance.
   However, workflow-level is more general than application-level provenance, as it enables collection in any workflow written for that modified engine [@freireProvenanceComputationalTasks2008].

3. **System-level provenance**: use operating system facilities to report the inputs and outputs that a process makes.
   System-level provenance is the least semantically aware because it does not even know dataflow, just a history of inputs and outputs, but it is the most general, because it supports any process (including any application or workflow engine) that uses watchable I/O operations [@freireProvenanceComputationalTasks2008].

Operating system-level provenance tracing (henceforth **SLRP**) is the most widely applicable form of provenance tracing; install an SLRP, and all unmodified applications, programming languages, and workflow engines will be traced.
This work focuses on system-level, retrospective provenance (SLRP).

SLRP has the following design features:

- **Completeness**:
   The SLRP should trace as many sources of information from the host as possible, although there are some that may be too impractical to trace.


   <!-- Make and workflow engines require user to specify a dependency graph (prospective provenance) by hand, which is often unsound in practice; i.e., the user may misses some dependencies and therefore types `make clean`. -->
   <!-- A tool could correctly determine which commands need to be re-executed based on SLRP without needing the user to specify anything. -->


- **User-level**:
   SLRP should be able to implemented at a user-level as opposed to kernel-level.
   Non-privilege implies user-level, but user-level does not imply non-privilege.
   
- **TODO**

# Prior work {#sec:prior-work}

There have been several methods of tracing SLRP proposed in prior work:

<!-- TODO:
- List every prior work for each method
- Cite numbers for performance
- Check on that our claims on the other constraints are correct
-->

- **Virtual machines**: running the application in a virtual machine that tracks information flow.
  This method is extremely slow; e.g., PANORAMA has 20x overhead [@yinPanoramaCapturingSystemwide2007].

- **Recompiling with instrumentation**: recompile, where the compiler or libraries insert instructions that log provenance data, e.g., [@maMPIMultiplePerspective2017].
  This method is not transparent.

- **Static/dynamic binary instrumentation**: either before run-time (static) or while a binary is running (dynamic) change the binary to emit provenance data [@leeHighAccuracyAttack2017].
  This method requires special hardware (Intel CPU) and a proprietary tool (Intel PIN).

- **Kernel modification**: modify the kernel directly or load a kernel module that traces provenance information, e.g., [@pasquierPracticalWholesystemProvenance2017].
  This method is neither non-privileged nor user-level.

- **Use kernel auditing frameworks**: use auditing frameworks already built in to the kernel (e.g., Linux/eBPF, Linux/auditd, Windows/ETW).
  This method is not non-privileged.

- **User-level debug tracing**: use user-level debug tracing functionality provided by the OS (e.g, Linux/ptrace used by strace, CDE [@guoCDEUsingSystem2011], SciUnit [@phamUsingProvenanceRepeatability2013], Reprozip [@chirigatiReproZipComputationalReproducibility2016], RR [@ocallahanEngineeringRecordReplay2017]).

- **Library interposition**: replace a standard library with an instrumented library that emits provenance data as appropriate.
  This could use the `LD_PRELOAD` of Linux and `DYLD_INSERT_LIBRARIES` on MacOS.

If non-privilege, transparency, no special hardware, and performance overhead less than 10-times are hard-requirements, the only possible methods are user-level debug tracing and library interposition.

In user-level debug tracing, the tracer runs in a separate process than the tracee.
Every time the tracee does a system call, control switches from the tracee to the kernel to the tracer and back and back [@fig:ptrace].
This path incurs two context switches for every system call.

On the other hand, in library interposition, the tracer code is part of a library dynamically loaded into the tracee's memory space.
While this imposes restrictions on the tracer code, it eliminates the extra context switches [@fig:lib-interpose].

<div id="fig:figureRef">

![Sequence diagram of process with user-level debug tracing](./ptrace.svg){#fig:ptrace width=40%}

![Sequence diagram of process with library interposition](./lib_interpose.svg){#fig:lib-interpose width=40%}

</div>

<!--
TODO:
Prior SLRP:
- PASS
- PASSv2
- CamFlow
- OPUS

Prior works that are substantially related to SLRP:
- RR
- strace
- fsatrace
- SciUnit
- ReproZip
- BubbleWrap
- Seccomp
- eBPF

Prior surveys/SoK
- Freire et al. Provenance for Computational Tasks: A Survey
- Oliveira et al. Provenance Analytics for Workflow-Based Computational Experiments: A Survey
- SoK by Inam et al. https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=10179405
- Pimentel et al. A Survey on Collecting, Managing, and Analyzing Provenance from Scripts
- our prior 2024 ACM REP work

-->

TODO: Matrix:

- Each row is a group of prior works

- Each column is an SLRP tracer-feature

Prior works argue that library interposition is not appropriate for SLRP for the following reasons:

- **Bypassable by direct system calls**

- **Fragility due to variations in C libraries**

- **Breaks other applications that use preloading**

- **Requires rebuilding or re-linking**

- **TODO**

> A common technique for intercepting system calls inprocess is to use dynamic linking to interpose wrapper functions over the C library functions that make system calls. In practice, we have found that method to be insufficient, due to applications making direct system calls, and fragile, due to variations in C libraries, and applications that require their own preloading [37, 3].

> An alternative implementation of whole-system provenance is interposition between system calls and libraries in user space, as in OPUS [9]. An argument in favour of such systems is that modifications to existing libraries are more likely to be adopted than modifications to the kernel. However, for this approach to work, all applications in the system need to be built against, or dynamically linked to, provenance-aware libraries, replacing existing libraries.

# Concepts {#sec:design}

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
Modification time can be manipulated by the user, either setting to the current time with `touch` (very common) or resetting to an arbitrary time with `utimes` (very uncommon).
Setting to the current time creates a new version which does not threaten the soundness of PROBE.
Setting to an arbitrary time and choosing a time already observed by PROBE does threaten its soundness.
For this reason, we consider the file size as a "backup distinguishing feature".
We consider it very unlikely that a non-malicious user would accidentally reset the time to the exact time (nanosecond resolution) we already observed and have the exact same size.

In the event of a data race on a file write, the dataflow graph generated by our approach ensures that all potential dependencies are captured as edges. The child processes of a parent process inherit write access to a file opened by the parent and are treated as dependencies of the incremented final version of the file. This guarantees that no critical dependency is overlooked, ensuring the soundness of the dataflow graph. However, the approach may not achieve completeness, as some processes with write access may not represent true dependencies. Since we have limited information about the order in which the shared file is accessed by the processes and the exact change made to the file, this approach uses the access mode effectively to construct a graph that prioritizes soundness. 

# Implementation {#sec:implementation}

The core of PROBE is a library interposer for libc, called `libprobe.so`.
`libprobe.so` exports wrappers for I/O functions like `open(...)`.
The wrappers:

1. log the call with arguments
2. forward the call to the _true_ libc implementation
3. log the underlying libc's returned value
4. return the underlying libc's returned value

There is no data shared between threads as the log is thread-local.
The dynamic-trace consists of information that was collected at a thread-local level, but can be aggregated into a global-level dataflow graph as described in @Sec:design.

To make logging as fast as possible, the log is a memory-mapped file.
If the logged data exceeds the free-space left in the file, `libprobe.so` will allocate a new file big enough for the allocation.
After the process dies, these log files can be stitched together into a single dynamic trace.

PROBE has a command-line interface. The `record` subcommand:

1. sets `LD_PRELOAD` to load `libprobe.so`
2. runs the user's provided command
3. stitches the PROBE data files into a single, readable log for other programs

There are also several subcommands that analyze or export the provenance.
Those subcommands generally use the dataflow representation rather than the PROBE dynamic trace.

<!-- TODO: discuss persistent prov -->

<!-- TODO: discuss applications -->

# Completeness analysis  {#sec:completeness-analysis}

We read the GNU C Library manual^[<https://www.gnu.org/software/libc/manual/html_node/>] and wrapped every function that does file I/O or changes how paths are resolved (e.g., `chdir`) in the following chapters, with the exception of redundant functions^[
One function, A, is redundant to another one B, if I/O through A necessitates a call through B.
We need only wrap B to discover that I/O will occur.
For example, we need only log file openings and closings, not individual file reads and writes.
]:

- Chapter 12. Input/Output on Streams
- Chapter 13. Low-Level Input/Output
- Chapter 14. File System Interface
- Chapter 15. Pipes and FIFOs
- Chapter 16. Sockets
- Chapter 26. Processes

Our research prototype wraps:

- file `open` and `close` family of functions^[The "family of functions" includes 64-bit variants, `f*` variants (`fopen`), re-open, close-range]
- `chdir` family of functions
- directory opens, closes, and iterations families of functions
- file `stat` and `access` families of functions
- file `chown`, `chmod`, and `utime` families of functions
- `exec` family of functions
- `fork`, `clone`, `wait` families of functions
- `pthread_create`, `pthread_join`, `thrd_create`, `thrd_join`, etc. functions

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

<!-- # Threats to validity -->

<!-- # Conclusion -->

# Future work {#sec:future-work}

- Improve completeness: static binary rewriting
- Improve performance
- Multi-node and HPC cases

## Performance analysis {#sec:performance-analysis}

We intend to do a performance analysis by studying commonly used scientific applications.
We will sample popular projects from several repositories and run them in PROBE including:

- Spack packages, filtering for packages that contain an executable, and using each package's project's GitHub repo's stars as a measure of popularity
- Kaggle notebooks, using the number of stars as popularity
- WorkflowHub, using the number of citations of the associated DOI as a measure of popularity

<!--
- Hinsen's stack:
  - Project-specific code
  - Tutorials for scientific infrastructure are hypothetical to project-specific codes
  - Benchmarks of scientific infrastructure intended to mimic patterns of project-specific code

Scientific applications:

- Non-HPC-scale numerical applications
  - Sample from: WorkflowHub, Snakemake Worklow Catalog, Nf-core, UseGalaxy.eu, xSDK packages
  - Comp chem
  - Comp bio info
  - Comp phys
  - Comp astro
  - Earth science
  - Machine learning (non GPU side, data cleaning)
  - Generic data analysis
  - Lots of benchmarks here
- Client/server programs
  - Jupyter notebooks
    - Sample popular Kaggle notebooks
- Package management
  - Spack
  - Conda
  - Pip
- Benchmarks from ACM REP prior work

Big matrix

- **RQ1:** What is the overhead of PROBE compared to prior work on scientific benchmarks?
  - Root-level system-provenance tracers, Workflow-level provenance tracers
-->


<!--
- Specific quesitons for Dan/Darko
- Help with writing from Dan/Darko
- Future venue plan
- Email draft to dept (Josh, Jay)

- USENIX Workshop on the Theory and Practice of Provenance (TaPP)
  - 3 Expressiveness Benchmarking for System-Level Provenance https://www.usenix.org/conference/tapp17/workshop-program/presentation/chan
  - 5 Decoupling Provenance Capture and Analysis from Execution https://www.usenix.org/conference/tapp15/workshop-program/presentation/stamatogiannakis
- eScience
  - 1 A Method for Constructing Research Data Provenance in High-Performance Computing Systems https://doi.org/10.1109/e-Science58273.2023.10254932
  - 2 Application of BagIt-Serialized Research Object Bundles for Packaging and Re-Execution of Computational Analyses https://doi.org/10.1109/eScience.2019.00068
  - 22 Sciunits: Reusable Research Objects https://doi.org/10.1109/eScience.2017.51
- Giga Science
  -  60 Sharing interoperable workflow provenance: A review of best practices and their practical application in CWLProv https://doi.org/10.1093/gigascience/giz095
- Data Science
  - 119 Packaging research artefacts with RO-Crate https://doi.org/10.3233/DS-210053
- Journal of Biomedical Semantics
  - 7 End-to-End provenance representation for the understandability and reproducibility of scientific experiments using a semantic approach https://doi.org/10.1186/s13326-021-00253-1
- Data Science and Engineering
  - 37 Provenance-Aware Knowledge Representation: A Survey of Data Models and Contextualized Knowledge Graphs https://doi.org/10.1007/s41019-020-00118-0
- Web Information Systems Engineering
  - 8 ProvONE+: A Provenance Model for Scientific Workflows https://doi.org/10.1007/978-3-030-62008-0_30
- VLDB
  - 10 Improving reproducibility of data science pipelines through transparent provenance capture https://doi.org/10.14778/3415478.3415556
- ACM Symposium on Cloud Computing (SoCC)
  - 103 Practical whole-system provenance capture https://doi.org/10.1145/3127479.3129249
- Procedia of CS
  - 9 Facilitating the Reproducibility of Scientific Workflows with Execution Environment Specifications https://doi.org/10.1016/j.procs.2017.05.116
- International Conference on Parallel Architecture and Compilation Techniques (PACT)
  - 10 Lightweight Provenance Service for High-Performance Computing https://doi.org/10.1109/PACT.2017.14
- International conference on the management of data (SIGMOD)
  - 83 ReproZip: Computational Reproducibility With Ease https://dl.acm.org/doi/10.1145/2882903.2899401
-->
