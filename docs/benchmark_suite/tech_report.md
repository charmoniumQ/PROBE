# Literature search results

# Selected/rejected provenance collectors

| Tool                                                               | Method                       | Status                     |
|--------------------------------------------------------------------|------------------------------|----------------------------|
| strace                                                             | tracing                      | Reproduced                 |
| fsatrace                                                           | tracing                      | Reproduced                 |
| rr \cite{ocallahanEngineeringRecordReplay2017}                     | tracing                      | Reproduced                 |
| ReproZip \cite{chirigatiReproZipComputationalReproducibility2016}  | tracing                      | Reproduced                 |
| CARE \cite{janinCAREComprehensiveArchiver2014}                     | tracing                      | Reproduced                 |
| Sciunit \cite{phamUsingProvenanceRepeatability2013}                | tracing                      | Reproduced/rejected        |
| PTU \cite{phamUsingProvenanceRepeatability2013}                    | tracing                      | Reproduced/rejected        |
| CDE \cite{guoCDEUsingSystem2011}                                   | tracing                      | Reproduced/rejected        |
| ltrace                                                             | tracing                      | Reproduced/rejected        |
| SPADE \cite{gehaniSPADESupportProvenance2012}                      | audit, FS, or compile-time   | Needs more time            |
| DTrace \cite{DTrace}                                               | audit                        | Needs more time            |
| eBPF/bpftrace                                                      | audit                        | Needs more time            |
| SystemTap \cite{prasadLocatingSystemProblems2005}                  | audit                        | Needs more time            |
| PROV-IO \cite{hanPROVIOOCentricProvenance2022}                     | lib. ins.                    | Needs more time            |
| OPUS \cite{balakrishnanOPUSLightweightSystem2013}                  | lib. ins.                    | Not reproducible           |
| CamFlow \cite{pasquierPracticalWholesystemProvenance2017}          | kernel ins.                  | Requires custom kernel     |
| Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}                   | kernel ins.                  | Requires custom kernel     |
| LPM/ProvMon \cite{batesTrustworthyWholeSystemProvenance2015}       | kernel ins.                  | Requires custom kernel     |
| Arnold\cite{devecseryEideticSystems2014}                           | kern ins.                    | Requires custom kernel     |
| LPS \cite{daiLightweightProvenanceService2017}                     | kern ins.                    | Requires custom kernel     |
| RecProv \cite{jiRecProvProvenanceAwareUser2016}                    | tracing                      | No source                  |
| FiPS \cite{sultanaFileProvenanceSystem2013}                        | FS                           | No source                  |
| Namiki et al. \cite{namikiMethodConstructingResearch2023}          | audit                        | No source                  |
| LPROV \cite{wangLprovPracticalLibraryaware2018}                    | kernel mod., lib. ins.       | No source                  |
| S2Logger \cite{suenS2LoggerEndtoEndData2013}                       | kernel mod.                  | No source                  |
| ProTracer \cite{maProTracerPracticalProvenance2016}                | kernel mod.                  | No source                  |
| PANDDE \cite{fadolalkarimPANDDEProvenancebasedANomaly2016}         | kernel ins., FS              | No source                  |
| PASS/Pasta \cite{muniswamy-reddyProvenanceAwareStorageSystems2006} | kernel ins., FS, lib. ins.   | No source                  |
| PASSv2/Lasagna \cite{muniswamy-reddyLayeringProvenanceSystems2009} | kernel ins.                  | No source                  |
| Lineage FS \cite{sarLineageFileSystem}                             | kernel ins.                  | No source                  |
| RTAG \cite{jiEnablingRefinableCrossHost2018}                       | bin. ins.                    | No source                  |
| BEEP \cite{leeHighAccuracyAttack2017}                              | bin. ins.                    | Requires HW                |
| libdft \cite{kemerlisLibdftPracticalDynamic2012}                   | bin., kernel, lib. ins.      | Requires HW                |
| RAIN \cite{jiRAINRefinableAttack2017}                              | bin. ins.                    | Requires HW                |
| DataTracker \cite{stamatogiannakisLookingBlackBoxCapturing2015}    | compile-time ins.            | Requires HW                |
| MPI\cite{maMPIMultiplePerspective2017}                             | compile-time ins.            | Requires recompilation     |
| LDX \cite{kwonLDXCausalityInference2016}                           | VM ins.                      | Requires recompilation     |
| Panorama \cite{yinPanoramaCapturingSystemwide2007}                 | VM ins.                      | VMs are too slow           |
| PROV-Tracer \cite{stamatogiannakisDecouplingProvenanceCapture2015} | audit                        | VMs are too slow           |
| ETW \cite{EventTracingWin322021}                                   | audit                        | Not for Linux              |
| Sysmon \cite{markrussSysmonSysinternals2023}                       | audit                        | Not for Linux              |
| TREC \cite{vahdatTransparentResultCaching1998}                     | tracing                      | Not for Linux              |
| URSprung \cite{rupprechtImprovingReproducibilityData2020}          | audit                        | Not for Linux\footnotemark |
| Ma et al. \cite{maAccurateLowCost2015}                             | audit                        | Not for Linux              |
| ULTra \cite{burtonWorkloadCharacterizationUsing1998}               | tracing                      | Not for Linux              |

: Accepted provenance collectors.

| Tool                                                  | Reason                                                          |
|-------------------------------------------------------|-----------------------------------------------------------------|
| ES3 [@frewES3DemonstrationTransparent2008]            | specific to ES3 platform                                        |
| Chimera [@fosterChimeraVirtualData2002]               | specific to Chimera platform                                    |
| INSPECTOR [@thalheimInspectorDataProvenance2016a]     | doesn't track files                                             |
| MCI [@jiEnablingRefinableCrossHost2018]               | offline; depends on online-LDX                                  |
| OmegaLog [@hassanOmegaLogHighFidelityAttack2020]      | depends on app-level logs                                       |
| LogGC [@leeLogGCGarbageCollecting2013]                | contribution is deleting irrelevant events in the logs          |
| UIScope [@yangUISCOPEAccurateInstrumentationfree2020] | captures UI interactions; uses ETW to capture I/O operations    |
| Winnower [@hassanScalableClusterAuditing2018]         | specific to Docker Swarm                                        |

: Excluded provenance collectors.

# Implemented Benchmarks

Of these, @Tbl:prior-benchmarks shows the benchmarks used to evaluate each tool, of which there are quite a few.
We prioritized implementing frequently-used benchmarks, easy-to-implement benchmarks, and benchmarks that have value in representing a computational science use-case.

| Prior works | This work | Instances     | Benchmark group and examples from prior work         |
|-------------|-----------|---------------|------------------------------------------------------|
| 12          | yes       | 5             | HTTP server/traffic                                  |
| 10          | yes       | 2             | HTTP server/client                                   |
| 10          | yes       | 8             | Compile user packages                                |
| 9           | yes       | 19 + 1        | I/O microbenchmarks (lmbench + Postmark)             |
| 9           | no        |               | Browsers                                             |
| 6           | yes       | 3             | FTP client                                           |
| 5           | yes       | 1             | FTP server/traffic                                   |
| 5           | yes       | $5 \times 2$  | Un/archive                                           |
| 5           | yes       | 5             | BLAST                                                |
| 5           | yes       | 10            | CPU benchmarks (SPLASH-3)                            |
| 5           | yes       | 8             | Coreutils and system utils                           |
| 3           | yes       | 2             | cp                                                   |
| 2           | yes       | 2             | VCS checkouts                                        |
| 2           | no        |               | Sendmail                                             |
| 2           | no        |               | Machine learning workflows (CleanML, Spark, ImageML) |
| 1           | no        |               | Data processing workflows (VIC, FIE)                 |
| 1           | no        |               | Benchmarks occurring in only one prior work          |

: The number of prior works containing each benchmark

Benchmarks occuring in only one prior work include: RUBiS, x64, mysqld, gocr, Memcache, Redis, php, pybench, ping, mp3info, ngircd, CUPS

# Rejected benchmarks

| Number of prior works | Class                              | Reason for exclusion                                  |
|---|--------------------------------------------------------|-------------------------------------------------------|
| 7 | Text-based browsers (w3m, lynx, elinks)                | Interactive                                           |
| 7 | TUI apps (Vim, nano, sysstat, mc, emacs, alpine, pine) | Interactive                                           |
| 5 | GUI apps                                               | Interactive                                           |
| 1 | Windows programs (Notepad, Paint, IE)                  | Wrong platform                                        |
| 1 | gif2png                                                | Unknown program (dozens of programs called "gif2png") |
| 1 | Vanderbilt                                             | Unknown program                                       |
| 1 | TextTransfer                                           | Unknown program                                       |
| 1 | DrawTool                                               | Unknown program                                       |
| 1 | yopsweb                                                | Unknown program                                       |

: Benchmarks rejected by this work

GUI apps include: xpdf, Audacious, Sublime Text, Notepad++, Evince, Krusader, Mplayer, mpv, Transmission, FileZilla, Pidgin

# Benchmark descriptions

The most common benchmark classes from prior work are, **HTTP servers/traffic**, **HTTP servers/clients**, **FTP servers/traffic**, and **FTP servers/clients** are popular because prior work focuses overwhelmingly on provenance for the sake of security (auditing, intrusion detection, or digital forensics).
While these benchmarks may not be specifically relevant for computational science workloads, we wanted to include them in our suite to improve our coverage of benchmarks used frequently in prior works.
We implemented 5 HTTP servers (ApacheHttpd, miniHTTP, Python's http.server, lighttpd, Nginx) running against traffic from Hey (successor to ApacheBench) and 2 HTTP clients (curl and Wget).
We implemented 1 FTP server (ProFTPD) running against traffic from httpbench^[See <https://github.com/selectel/ftpbench>] and 3 FTP clients (curl, Wget, and lftp).

**Compiling packages** from source is a common operation in computational science, so we implemented as many of these as we could and also implemented some of our own.
However, compiling glibc and LLVM takes much longer than everything else in the benchmark suite, so we excluded LLVM and glibc.
We implemented a pattern for compiling packages from Spack that discounts the time taken to download sources, counting only the time taken to unpack, patch, configure, compile, link, and install them.
We implemented compiling Python, HDF5, git, and Perl.

Implementing headless for **browsers** in "batch-mode" without GUI interaction is not impossibly difficult, but non-trivial.
Furthermore, we deprioritized this benchmark because few computational science applications resemble the workload of a web browser.

**Archive** and **unarchiving** is a common task for retrieving data or source code.
We benchmark un/archiving several archives with several compression algorithms.
Choosing a compression algorithm may turn an otherwise I/O-bound workload to a CPU-bound workload, which would make the impact of provenance tracing smaller.
We implemented archive and unarchiving a medium-sized project (7 MiB uncompressed) with no compression, gzip, pigz, bzip, and pbzip2.

**I/O microbenchmarks** could be informative for explicating which I/O operations are most affected.
Prior work uses lmbench [@mcvoyLmbenchPortableTools1996], which benchmarks individual syscalls, Postmark [@katcherPostMarkNewFile2005], which focuses on many small I/O operations (typical for web servers), IOR [@shanUsingIORAnalyze2007], H5bench [@liH5benchHDF5IO2021] and BT-IO^[See <https://www.nas.nasa.gov/software/npb.html>], which are specialized for parallel I/O on high-performance machines, and custom benchmarks, for example running open/close in a tight loop.
Since we did not have access to a high-performance machine, we used lmbench and Postmark.
We further restrict lmbench to the test-cases relevant to I/O and used by prior work.

**BLAST** [@altschulBasicLocalAlignment1990] is a search for a fuzzy string in a protein database.
However, unlike prior work, we split the benchmark into query groups described by Coulouris [@coulourisBlastBenchmark2016], since the queries have different performance characteristics:
blastn (nucleotide-nucleotide BLAST), megablast (large numbers of query sequences) blastp (protein-protein BLAST), blastx (nucleotide query sequence against a protein sequence database), tblastn (protein query against the six-frame translations of a nucleotide sequence database), tblastx (nucleotide query against the six-frame translations of a nucleotide sequence database).

Prior work uses several **CPU benchmarks**: SPEC CPU INT 2006 [@henningSPECCPU2006Benchmark2006], SPLASH-3 [@sakalisSplash3ProperlySynchronized2016], SPLASH-2 [@wooSPLASH2Programs1995] and HPCG [@herouxHPCGBenchmarkTechnical2013].
While we do not expect CPU benchmarks to be particularly enlightening for provenance collectors, which usually only affect I/O performance, it was used in three prior works, so we tried to implement both.
SPLASH-3 is an updated and fixed version of the same benchmarks in SPLASH-2.
However, SPEC CPU INT 2006 is not free (as in beer), so we could only implement SPLASH-3.

**Sendmail** is a quite old mail server program.
Mail servers do not resemble a computational science workload, and it is unclear what workload we would run against the server.
Therfore, we deprioritized this benchmark and did not implement it.

**VCS checkouts** are a common computational science operation.
We simply clone a repository (untimed) and run `${vcs} checkout ${commit}` for random commits in the repository.
CVS does not have a notion of global commits, so we use Mercurial and Git.

VIC, FIE, ImageML, and Spark are real-world examples of **Data processing** and **machine-learning workflows**.
We would like to implement these, but reproducing those workflows is non-trivial; they each require their own computational stack.
For FIE, in particular, there is no script that glues all of the operations together; we would have to read the publication [@billahUsingDataGrid2016] which FIE supports to understand the workflow, and write our own script which glues the operations together.

We did not see a huge representative value in **coreutils and friends (bash, cp, ls, procps)** that would not already be gleaned from lmbench, but due to its simplicity and use in prior work, we implemented it anyway.
For `bash`, we do not know what exact workload prior works are using, but we test the speed of incrementing an integer and changing directories (`cd`).

The **other** benchmark programs are mostly specific desktop applications used only in one prior work.
These would likely not yield any insights not already yielded by the benchmarks we implemented, and for each one we would need to build it from source, find a workload for it, and take the time to run it.
They weigh little in the argument that our benchmark suite represents prior work, since they are only used in one prior work.

# Codes for provenance collectors

The last column in the table categorizes the "state" of that provenance collector in this work into one of the following:

- **Not for Linux.**
  Our systems are Linux-based and Linux is used by many computational scientists.
  Therefore, we did not try to reproduce systems that were not Linux based.

- **VMs too slow.**
  Some provenance collectors require running the code in a virtual machine.
  We know a priori that these methods are prohibitively slow, with Panorama reporting 20x average overhead [@yinPanoramaCapturingSystemwide2007], which is too slow for practical use.

- **Requires recompilation.**
  Some provenance collectors require users to recompile their entire application and library stack.
  Recompiling is prohibitively onerous and negates the otherwise low cost of switching to system-level provenance we are pursuing.

- **Requires special hardware.**
  Some methods require specific CPUs, e.g., Intel CPUs for a dynamic instrumentation tool called Intel PIN.
  Being limited to specific CPUs violates our goal of promulgating reproducibility to as many people as possible.
  
- **No source.**
  <!--TODO: Evaluate this first, so  "no source" AND "requires kernel changes" would be classified as "no source". Future work may be able to reproduce collectors which require kernel changes (or VMs), but has no chance of reproducing collectors which have no source.-->
  We searched the original papers, GitHub, BitBucket, Google (first fifty results), and emailed the first author (CCing the others).
  If we still could not find the source code for a particular provenance collector, we cannot reproduce it.
  Note that RecProv is implemented using rr, so we can use rr as a lower-bound for RecProv.
  
- **Requires custom kernel (Hi-Fi, LPM/ProvMon, CamFlow).**
  Collectors that modify Linux kernel code are out-of-scope for this work due to their increased maintenance overhead, security risk, and difficulty of system administration.
  Indeed, many of the systems are too old to be usable: LPM/ProvMon is a patch-set for Linux 2.6.32 (reached end-of-life 2016), Hi-Fi is a patch-set for Linux 3.2 (reached end-of-life in 2018).
  On the other hand, SingularityCE/Apptainer requires Linux $\geq$ 3.8 for user namespaces.

<!-- - **Ancient kernel (Hi-Fi and LPM/ProvMon).** -->
<!--   Some provenance systems are implemented as patches into the Linux kernel. -->
<!--   As time passed, these grew out-of-date with modern Linux kernels. -->
<!--   We deprioritized the implementation of these methods because they require extermely old kernels, and thus may not be worthy of use in practical systems. -->
<!--   Even conservative Linux distributions like CentOS 7 use Linux 3.10. -->
<!--   This difficulty is not a bug in our study, but reflects an underlying reality that modified kernels are less likely to be maintained. -->
<!--   However, if we had more time, we would want to reproduce these systems too. -->

<!-- - **Need more time for kernel (CamFlow).** -->
<!--   Provenance systems that are implemented as patches on the Linux kernel are difficult to deploy, even if the kernel is recent. -->
<!--   We could implement experimental infrastructure to run the modified kernel on "bare metal", which is difficult to set up and dangerous, or we could run the modified kernel in a traditional virtual machine, which would distort the runtimes non-linearly from native performance and invalidate the predictive performance model, or a cycle-accurate virtual machine, which would prohibitively slow down the benchmark suite to the point that we would have much less data. -->
<!--   Nevertheless, we would like to implement this system in a cycle-accurate virtual machine like gem5, if we had more time. -->

- **Not reproducible (OPUS).**
  We tried to get this provenance system to run with several weeks of effort: we emailed the original authors and other authors who used this system, and we left a GitHub issue describing the expected and actual results ^[See <https://github.com/dtg-FRESCO/opus/issues/1>].
  However, we still could not get the system to run correctly.
  
- **Needs more time (DTrace, SPADE, eBPF/bpftrace).**
  We simply needed more time to implement these provenance collectors.

- **Reproduced/rejected (ltrace, CDE, Sciunit, PTU).**

  - While we could run **ltrace** on some of our benchmarks, it crashed when processing on the more complex benchmarks, for example FTP server/client.
    We localized the problem to the following code^[See <https://gitlab.com/cespedes/ltrace/-/blob/8eabf684ba6b11ae7a1a843aca3c0657c6329d73/handle_event.c#L775>]:

    ``` c
    /* FIXME: not good -- should use dynamic allocation. 19990703 mortene. */
    if (proc->callstack_depth == MAX_CALLDEPTH - 1) {
     fprintf(stderr, "%s: Error: call nesting too deep!\n", __func__);
     abort();
     return;
    }
    ```

  - **CDE** can run some of our benchmarks, but crashes on others, for example BLAST.
    The crash occurs when trying to copy from the tracee process to the tracer due to `ret == NULL`[^cde-note]:

    ```c
    static char* strcpy_from_child(struct tcb* tcp, long addr) {
      char* ret = strcpy_from_child_or_null(tcp, addr);
      EXITIF(ret == NULL);
      return ret;
    }
    ```

    \normalsize

    The simplest explanation would be that the destination buffer is not large enough to store the data that `strcpy` wants to write. However, the destination buffer is `PATHMAX`.

    [^cde-note]: See <https://github.com/usnistgov/corr-CDE/blob/v0.1/strace-4.6/cde.c#L2650>

  - **PTU** seems to work on most test cases outside of our BenchExec container.
    However, there is a bug causing it to crash inside our container.

  - **Sciunit** works on most benchmarks, but exhausts the memory of our system when processing FTP server/client and Spack compile package.
    We believe this is simply due to the benchmarks manipulating a large number of files and Sciunit trying to deduplicate them all.

- **Reproduced (strace, fsatrace, RR, ReproZip, CARE).**
  We reproduced this provenance collector on all of the benchmarks.

# Open source contributions

The actual benchmark set and statistical analysis are open-source:

- <https://github.com/charmoniumQ/prov-tracer/>

This work necessitated modifying Spack, Sciunit, PTU, jupyter-contrib-nbextensions, Nixpkgs, ftpbench, and benchexec.
Where appropriate, we submitted as pull-requests to the respective upstream projects.

The following are merged PRs developed as a result of this work:

- <https://github.com/depaul-dice/sciunit/pull/35>
- <https://github.com/spack/spack/pull/42159>
- <https://github.com/spack/spack/pull/42199>
- <https://github.com/spack/spack/pull/42114>
- <https://github.com/selectel/ftpbench/pull/5>
- <https://github.com/selectel/ftpbench/pull/4>
- <https://github.com/sosy-lab/benchexec/pull/984>
- <https://github.com/NixOS/nixpkgs/pull/263829>
- <https://github.com/NixOS/nixpkgs/pull/257396>

The following are open PRs developed as a result of this work:

- <https://github.com/spack/spack/pull/39902>
- <https://github.com/spack/spack/pull/42131>
- <https://github.com/spack/spack/pull/41048>
- <https://github.com/sosy-lab/benchexec/pull/990>
- <https://github.com/depaul-dice/sciunit/pull/36>
- <https://github.com/depaul-dice/provenance-to-use/pull/4>
- <https://github.com/depaul-dice/provenance-to-use/pull/5>
- <https://github.com/ipython-contrib/jupyter_contrib_nbextensions/pull/1649>
- <https://github.com/NixOS/nixpkgs/issues/268542>

# Full-size plots

\begin{figure*}
\begin{center}
\includegraphics[width=0.98\textwidth]{generated/dendrogram_full.pdf}
\caption{
  \textcolor{myred}{
  Dendrogram showing the distance between clusters.
  See \Cref{fig:dendrogram} for details.
  \textit{Figure removed.}
  }
}
\label{fig:dendrogram-full}
\end{center}
\end{figure*}
