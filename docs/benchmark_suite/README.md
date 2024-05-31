---
from: markdown
verbosity: INFO
citeproc: yes
ccite-method: citeproc
publisher:
  copyrightYear: 2024
  year: 2024
  copyright: rightsretained
  booktitle: ACM Conference on Reproducibility and Replicability (ACM REP '24), June 18--20, 2024, Rennes, France
  doi: 10.1145/3641525.3663627
  isbn: 979-8-4007-0530-4/24/06
  conference:
    acronym: ACM REP '24
    name: ACM Conference on Reproducibility and Replicability
    daterange: June 18--20, 2024
    location: Rennes, France
bibliography:
  - zotero
  - reed
  - supplemental
link-citations: yes
link-bibliography: yes
notes-after-punctuation: yes
title: A benchmark suite and performance analysis of user-space provenance collectors
author:
  - name: Samuel Grayson
    orcid: 0000-0001-5411-356X
    email: grayson5@illinois.edu
    affiliation:
      institution: University of Illinois Urbana-Champaign
      department:
        - Department of Computer Science
      streetaddress:  201 North Goodwin Avenue MC 258
      city: Urbana
      state: IL
      country: USA
      postcode: 61801-2302
  - name: Faustino Aguilar
    orcid: 0009-0000-1375-1143
    email: faustino.aguilar@up.ac.pa
    affiliation:
      institution: University of Panama
      department:
        - Department of Computer Engineering
      city: Panama City
      country: Panama
  - name: Reed Milewicz
    orcid: 0000-0002-1701-0008
    email: rmilewi@sandia.gov
    affiliation:
      department:
        - Software Engineering and Research Department
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
        - Department of Computer Science
      streetaddress:  201 North Goodwin Avenue MC 258
      city: Urbana
      state: IL
      country: USA
      postcode: 61801-2302
classoption:
  - sigconf
  - screen=true
  - review=false
  - authordraft=false
  - timestamp=false
  - balance=false
  - pbalance=true
papersize: letter
pagestyle: plain
lang: en-US
standalone: yes # setting to yes calls \maketitle
number-sections: yes
indent: no
date: 2024-01-30
pagestyle: plain
papersize: letter
abstract: >
  Computational provenance has many important applications, especially to reproducibility.
  System-level provenance collectors can track provenance data without requiring the user to change anything about their application.
  However, system-level provenance collectors have performance overheads, and, worse still, different works use different and incomparable benchmarks to assess their performance overhead.
  This work identifies user-space system-level provenance collectors in prior work, collates the benchmarks, and evaluates each collector on each benchmark.
  We use benchmark minimization to select a minimal subset of benchmarks, which can be used as goalposts for future work on system-level provenance collectors.
---

# Introduction

In the past decade, this has inspired a diverse range of research and development efforts meant to give us greater control over our software, including containers and virtual machines to capture environments [@boettiger2015introduction; @nust2020ten; @jansen2020curious; @satyanarayanan2023towards], package managers for fine-grained management of dependencies [@gamblin2015spack; @kowalewski2022sustainable], interactive notebooks and workflows [@beg2021using; @di2017nextflow; @koster2012snakemake], and online platforms for archiving and sharing computational experiments [@goecks2010galaxy; @stodden2012runmycode; @stodden2015researchcompendia; @chard2019implementing].
In this work, we focus on **computational provenance** as a complementary strategy for managing reproducibility across the research software lifecycle.
Computational provenance is the history of a computational task, describing the artifacts and processes that led to or influenced the result [@freireProvenanceComputationalTasks2008]; the term encompasses a spectrum of tools and techniques ranging from simple logging to complex graphs decorated with sufficient detail to replay a computational experiment.

Provenance data can provide crucial information about the hardware and software environments in which a code is executed.
The use cases for this data are numerous and many different tools for collecting it have been independently developed.
However a rigorous comparison of those available tools and the extent to which they are practically usable in CSE application contexts has been lacking from prior work.
To summarize the state of the art and to establish goalposts for future research in this area, our paper makes the following contributions:

- *A rapid review on available system-level provenance collectors*.
  We identify 45 provenance collectors from prior work, classify their method of operation, and attempt to reproduce the ones that meet specific criteria.
  We successfully reproduced 9 out of 15 collectors that met our criteria.

- *A benchmark suite for system-level provenance collectors*:
  Prior work does not use a consistent set of benchmarks; publications often use an overlapping set of benchmarks from their prior work.
  We find the superset of all benchmarks used in the prior work, identify unrepresented areas, and find a statistically valid subset of the benchmark.
  Our benchmark subset is able to recover the original benchmark results within 5% of the actual value 95% of the time.

The remainder of the paper is structured as follows.
\Cref{background} motivates provenance and describe the different methods of collecting it.
\Cref{methods} describes how we execute the rapid review, implement and execute benchmarks, and statistically subset the results.
\Cref{results} shows the results of the rapid review, performance experiment, and benchmark subsetting.
\Cref{discussion} explains what the results show and touches on some problems they bring up.
\Cref{conclusion} summarizes the work.

# Background

As one *Nature* editoralist put it, "behind every great scientific finding of the modern age, there is a computer" [@perkel2021ten].
The production of scientific results now often involve complex and lengthy operations on hardware and software systems;
transparency is fundamental to the practice of science, and increasing the transparency of those processes is the end goal of provenance research.

A recent Department of Energy Advanced Scientific Computing Research report by Heroux et al. has called for further research to develop solutions for highly automatic and portable provenance capture and replay[@heroux2023basic].
The potential applications are numerous.
We include only a few notable applications [@pimentelSurveyCollectingManaging2019; @sarLineageFileSystem]):

1. **Reproducibility**.
   A description of the inputs and processes used to generate a specific output can aid manual and automatic reproduction of that output[^acm-defns].
   Provenance data improves **manual reproducibility**, because users have a record of the inputs, outputs, and processes used to create a computational artifact.
   Provenance data also has the potential to enable **automatic reproducibility**, if the process trace is detailed enough to be "re-executed".
   This idea is also called "software record/replay".
   Automatic reproduciblity opens itself up to other applications, like saving space by deleting results and regenerating them on-demand.
   However, not all provenance collectors make this their goal.

   [^acm-defns]: "Reproduction", in the ACM sense, where a **different team** uses the **same input artifacts** to generate the output artifact [@acminc.staffArtifactReviewBadging2020].

2. **Caching subsequent re-executions**.
   Computational science inquiries often involve changing some code and re-executing the workflows (e.g., testing different clustering algorithms).
   In these cases, the user has to keep track of what parts of the code they changed, and which processes have to be re-executed.
   However, an automated system could read the computational provenance graphs produced by previous executions, look at what parts of the code changed, and safely decide what processes need to be re-executed.
   Unlike Make and CMake, which require the user to manually specify a dependency graph, a provenance-enabled approach could be automatic, mitigating the chance for a dependency misspecification.

3. **Comprehension**. 
   Provenance helps the user understand and document workflows and workflow results.
   An automated tool that consumes provenance can answer queries like "What version of the data did I use for this figure?" and "Does this workflow include FERPA-protected data?".
   A user might have run dozens of different versions of their workflow and may want to ask an automated system, "show me the results I previously computed based on that data with this algorithm?".

There are three high-level methods by which one can capture computational provenance: **application-level** (modifying an application to report provenance data), **workflow-level**, (leveraging a workflow engine or programming language to report provenance data), and **system-level** (leveraging an operating system to report provenance data) [@freireProvenanceComputationalTasks2008].
Application-level provenance is the most semantically rich but the least general since it only applies to particular applications modified to disclose provenance.
Workflow- and language-level provenance is a middle ground between semantic richness and generality, applying to all programs using a certain workflow or programming language.
System-level provenance is the least semantically rich but most general, applying to all programs on that particular system.

<!--
**Application-level** provenance is the most semantically rich, since it knows the use of each input at the application-level, but the least general, since each application would have to be modified individually.
**Workflow-level** or **language-level** provenance is a middle ground in semantic richness and generality;
  it only knows the use of inputs in a dataflow sense, but all applications using the provenance-modified workflow engine or programming language would emit provenance data without themselves being modified to emit provenance data.
**System-level** is the most general, since all applications on the system would emit provenance data, but it is the least semantically rich, since observed dependencies may overapproximate the true dependencies.


System-level provenance collectors may be implemented in kernel-space or in user-space.
Since **kernel-space** provenance collectors modify internals of the Linux kernel, keeping them up-to-date as the kernel changes is a significant maintenance burden.
High-security national labs may be wary of including a patched kernel.
On the other hand, **user-space collectors** compromise performance in exchange for requiring less maintenance and less privilege.
-->

The implementation cost of adopting system-level provenance in a project that currently has no provenance is low because the user need not change _anything_ about their application or workflow;
  they merely need to install some provenance collector onto their system and rerun their application.
Although the user may eventually use a more semantically rich provenance, low-initial-cost system-level provenance would get provenance's "foot in the door".
Since system-level provenance collection is a possibly valuable tradeoff between implementation cost and enabling provenance applications, system-level provenance will be the subject of this work.

In the context of system-level provenance, artifacts are usually files or processes.
Operations are usually syscalls involving artifacts, e.g., `fork`, `exec`, `open`, `close`.
For example, suppose a bash script runs a Python script that uses matplotlib to create a figure.
A provenance collector may record the events in @Fig:prov-example, including all file dependencies of the process, without knowledge of the underlying program or programming language.

\begin{figure}
\begin{center}
\includegraphics[width=0.4\textwidth]{prov-example.pdf}
\caption{Abridged graph of events a hypothetical system-level provenance collector might collect. This collector could infer files required for re-execution (including executables, dynamic libraries, scripts, script libraries, data) \emph{without} knowing anything about the program or programming language.}
\label{fig:prov-example}
\end{center}
\end{figure}

We defer to the cited papers for details on versioning artifacts [@balakrishnanOPUSLightweightSystem2013] and cycles [@muniswamy-reddyProvenanceAwareStorageSystems2006].
Some collectors may also record calls to network resources, the current time, process IPC, and other interactions.
  
<!--
\begin{figure*}
\subcaptionbox{
  Application-level provenance has the most semantic information.
}{\includegraphics[width=0.22\textwidth]{app-lvl-prov.pdf}\label{fig:app-lvl-prov}}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Workflow-level provenance has an intermediate amount of semantic information.
}{\includegraphics[width=0.22\textwidth]{wf-lvl-prov.pdf}\label{fig:wf-lvl-prov}}
\hspace{0.03\textwidth}%
\subcaptionbox{
  System-level log of I/O operations.
}{\includegraphics[width=0.12\textwidth]{sys-lvl-log.pdf}\label{fig:sys-lvl-log}}
\hspace{0.03\textwidth}%
\subcaptionbox{
  System-level provenance, inferred from the log in Fig. 1c., has the least amount of semantic information
}{\includegraphics[width=0.22\textwidth]{sys-lvl-prov.pdf}\label{fig:sys-lvl-prov}}
\caption{Several provenance graphs collected at different levels for the same application.}
\label{fig:prov}
\end{figure*}
-->

While there is little additional programmer-time in using system-level provenance (no user code change), there is a non-trivial implicit overhead in monitoring and recording each computational process.
Even a minor overhead per I/O operation would become significant when amplified over the tens of thousands of I/O operations a program might execute per second.
Prior publications in system-level provenance usually contain benchmark programs to evaluate the overhead imposed by the system-level provenance tool.
However, the set of chosen benchmark programs is inconsistent from one publication to another, and overhead can be sensitive to the exact choice of benchmark, so these results are incomparable between publications.
Most publications only benchmark their new system against native/no-provenance, so prior work cannot easily establish which system-level provenance tool is the fastest.

## Prior work

Each result of our rapid review (@Tbl:tools) is an obvious prior work on provenance collection.
However, those priors studies look at only one or two competing provenance tools at a time.
To the best of our knowledge, there has been no global comparison of provenance tools.
ProvBench [@liuProvBenchPerformanceProvenance2022] uses 3 provenance collectors (CamFlow, SPADE, and OPUS), but they are solely concerned with the differences between representations of provenance, not performance.

On the other hand, benchmark subsetting is a well-studied area.
This work mostly follows Yi et al.'s publication [@yiEvaluatingBenchmarkSubsetting2006], which evaluates subsetting methodologies and determines that dimensionality reduction and clustering ar broadly good strategies.
Phansalkar et al. [@phansalkarSubsettingSPECCPU20062007] apply dimensionality reduction and clustering to SPEC CPU benchmarks.

# Methods

## Rapid Review

We preformed a rapid review to identify the research state-of-the-art tools for automatic system-level provenance.

Rapid Reviews are a lighter-weight alternative to systematic literature reviews with a focus on timely feedback for decision-making.
Schünemann and Moja [@schunemannReviewsRapidRapid2015] show that Rapid Reviews can yield substantially similar results to a systematic literature review, albeit with less detail.
Although developed in medicine, Cartaxo et al. show that Rapid Reviews are useful for informing software engineering design decisions [@cartaxoRoleRapidReviews2018; @cartaxoRapidReviewsSoftware2020].

We conducted a rapid review with the following parameters:

- **Search terms**: "computational provenance" and "system-level provenance" (two Google Scholar searches)

- **Search engine**: Google Scholar

- **Number of results**:
  50 of both searches.
  This threshold is the point of diminishing returns, as no new collectors came up in the 40th – 50th results.

- **Criteria**:
  A relevant publication would center on one or more operating system-level provenance collectors that capture file provenance.
  A tool requiring that the user use a specific application or platform would be irrelevant.

## Benchmark Selection

For each publication selected by the literature review, if it is a secondary study, we augment the set with the primary studies on which the secondary study is based.
In the augmented set, we aggregate all benchmarks that were used to evaluate the performance of provenance collectors.
THe benchmarks genrally programs like `tar xvf` that manipulate a large number of files.

We excluded benchmarks for which we could not even find the original program (e.g., TextTransfer), benchmarks that were not available for Linux (e.g., Internet Explorer), benchmarks with a graphical component (e.g., Notepad++), and benchmarks with an interactive component (e.g., GNU Midnight Commander).
We used Nix package manager to build the software environment, so the environment is buildable on many different platforms[^nix-footnote].

[^nix-footnote]: Nix has official installers for Linux, Mac OS X, and Windows Subsystem for Linux on i686, x86_64, and aarch64 architectures, but FreeBSD and OpenBSD both package Nix themselves, and it can likely be built from source on even more platforms. See <https://nixos.org/guides/how-nix-works>

We also added new benchmarks for data science and compiling-from-source.

## Performance Experiment

We run a complete matrix (every collector on every benchmark) 3 times in a random order on the machine described by @Tbl:machine.
We use CGroups [@beyerReliableBenchmarkingRequirements2019] to precisely measure the CPU time, wall time, memory utilization, and other attributes of the process (including child processes).
We enable ASLR, which introduces non-determinism into the execution time, but helpfully randomizes a variable that may otherwise have a confounding effect [@mytkowiczProducingWrongData2009].
We restrict the program to a single core to eliminate unpredictable scheduling and prevent other daemons from perturbing the experiment (they can run on the other N-1 cores).
We wrap the programs that exit quickly in loops so they take about 3 seconds without any provenance system, isolating the cold-start costs.

\begin{table}
\caption{Our experimental machine description.}
\label{tbl:machine}
%\begin{minipage}{\columnwidth}
\begin{center}
\small
\begin{tabular}{ll}
\toprule
Name   & Value                                          \\
\midrule
CPU    & 11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz \\
RAM    & 16 GiB of SODIMM DDR4 Synchronous 2400 MHz     \\
Kernel & Linux 6.1.64                                   \\
Disk   & Sandisk Corp WD Black SN770 250GB NVMe SSD \\
\bottomrule
\end{tabular}
\end{center}
%\end{minipage}
\end{table}

## Benchmark Subsetting

We implemented and ran many different benchmarks, which may be costly for future researchers seeking to evaluate new provenance collectors.
A smaller, less costly set of benchmarks may sufficiently represent the larger set.

Following Yi et al. [@yiEvaluatingBenchmarkSubsetting2006], we evaluate the benchmark subset in two different ways:

- **Accuracy**.
   How closely do features of the subset resemble features of the original set?
   We will evaluate this by computing the root mean squared error (RMSE) of a non-negative linear regression from the standardized features of selected benchmarks to the mean of features of the total set.

- **Representativeness.**
   How close are benchmarks in the original set to the closest benchmarks in the subset?
   We will evaluate this by computing RMSE on the euclidean distance of standardized features from each benchmark in the original set to the closest benchmark in the selected subset.

We use a non-negative linear regression to account for the possibility that the total set has unequal proportions of benchmark clusters.
We require the weights to be non-negative, so doing better on each benchmark in the subset implies a better performance on the total.
Finally, we normalize these weights by adding several copies of the following equation to the linear regression: $\mathrm{weight}_A + \mathrm{weight}_B + \dotsb = 1$.
Yi et al. [@yiEvaluatingBenchmarkSubsetting2006] used an unweighted average, perhaps because they could assume the benchmarks in SPEC CPU 2006 were already balanced.

We standardize the features by mapping $x$ to $z_x = (x - \bar{x}) / \sigma_x$.
While $x$ is meaningful in absolute units, $z_x$ is meaningful in relative terms (i.e., a value of 1 means "1 standard deviation greater than the mean").
Yi et al., by contrast, only normalize their features $x_{\mathrm{norm}} = x / x_{\max}$, which does not take into account the mean value.
We want our features to be measured relative to the spread of those features in prior work.

We score by RMSE over mean absolute error (MAE), used by Yi et al. [@yiEvaluatingBenchmarkSubsetting2006], because RMSE punishes outliers more.
MAE permits some distances to be large, so long it is made up for by shrinking other distances.
RMSE would prefer a more equitable distribution, which might be worse on average but better on the outliers than MAE.
We think this aligns more with the intent of "representativeness."

We will use features that are invariant between running a program ten times and running it once as features.
These features give long benchmarks and short benchmarks which exercise the same functionality similar vectorization.
In particular, we use:

1. The log overhead ratio of running the benchmark in each provenance collector.
   We use the logarithm of the ratio rather than the ratio directly because the ratio cannot be distributed symmetrically, but the logarithm may be[^log-footnote].

[^log-footnote]:
   Suppose some provenance collector makes programs take roughly twice as long but with a large amount of variance, so the expected value of the ratio is 2.
   A symmetric distribution would require the probability of observing a ratio of -1 for a particular program is equal to the probability of observing a ratio of 5, but a ratio of -1 is impossible, while 5 is possible due to the large variance.
   On the other hand, $\log x$ maps positive numbers (like ratios) to real numbers (which may be symmetrically distributed); choosing $2 \approx e^{0.3}$ as our center,  $5 \approx e^{0.7}$ and $0.9 \approx e^{-0.1}$ are equidistant in log-space (negative logs indicate a speedup rather than slowdown, which are theoretically possible when comparing two runtimes).
   Also note that exp(arithmean(log(x))) is the same as geomean(x), which is preferred over arithmean(x) for performance ratios according to Mashey \cite{masheyWarBenchmarkMeans2004}.

2. The ratio of CPU time to wall time.
   When limited to a single core on an unloaded system, wall time includes I/O, but CPU time does not.

3. The number of syscalls in each category per wall time second, where the categories consist of socket-related, file-metadata-related, directory-related, file-related, exec-related, fork-related, exit-related syscalls, IPC-related syscalls, and chdir syscalls.

In order to choose the subset, we will try clustering (k-means and agglomerative clustering with Ward linkage\footnote{k-means and agglomerative/Ward both minimize within-cluster variance, which is equivalent to minimizing our metric of "representativeness" defined earlier, although they minimize it in different ways: k-means minimizes by moving clusters laterally; Agglomerative/Ward minimizes by greedily joining clusters.}), preceded by optional dimensionality reduction by principal component analysis (PCA).
Once the benchmarks are grouped into clusters, we identify one benchmark from each of the $k$ clusters to consist the benchmark subset.
We will determine the best $k$ experimentally.

# Results

## Selected Provenance Collectors

@Tbl:tools shows the provenance collectors we collected and their qualitative features.
Because there are not many open-source provenance collectors in prior work, we also include the following tools, which are not necessarily provenance collectors, but may be adapted as such: strace, ltrace, fsatrace, and RR.
See \Cref{notable-provenance-collectors} for more in-depth description of notable provenance collectors.
The second column shows the "collection method" (see \Cref{collection-methods} for their exact definition).

To acquire the source code, we looked in the original publication for links, checked the first 50 results in GitHub, BitBucket, and Google for the prototype name (e.g., "LPROV"), and then tried emailing the original authors.
Several of the authors wrote back to say that their source code was not available at all, and some never wrote back.
We mark both as "No source".

Although we could reproduce ltrace, CDE, Sciunit, and PTU on _certain_ benchmarks, we couldn't reproduce them on all benchmarks, so we excluded them from further consideration.


\begin{table}
\caption{
  Provenance collectors from our search results and from experience.
  See \Cref{collection-methods} for their exact definition.
}
\label{tbl:tools}
%\begin{minipage}{\columnwidth}
\begin{center}
\footnotesize
\begin{tabular}{lll}
\toprule
Tool                                                               & Method                       & Status                     \\
\midrule
strace                                                             & tracing                      & Reproduced                 \\
fsatrace                                                           & tracing                      & Reproduced                 \\
rr \cite{ocallahanEngineeringRecordReplay2017}                     & tracing                      & Reproduced                 \\
ReproZip \cite{chirigatiReproZipComputationalReproducibility2016}  & tracing                      & Reproduced                 \\
CARE \cite{janinCAREComprehensiveArchiver2014}                     & tracing                      & Reproduced                 \\
Sciunit \cite{phamUsingProvenanceRepeatability2013}                & tracing                      & Reproduced/rejected        \\
PTU \cite{phamUsingProvenanceRepeatability2013}                    & tracing                      & Reproduced/rejected        \\
CDE \cite{guoCDEUsingSystem2011}                                   & tracing                      & Reproduced/rejected        \\
ltrace                                                             & tracing                      & Reproduced/rejected        \\
SPADE \cite{gehaniSPADESupportProvenance2012}                      & audit, FS, or compile-time   & Needs more time            \\
DTrace \cite{DTrace}                                               & audit                        & Needs more time            \\
eBPF/bpftrace                                                      & audit                        & Needs more time            \\
SystemTap \cite{prasadLocatingSystemProblems2005}                  & audit                        & Needs more time            \\
PROV-IO \cite{hanPROVIOOCentricProvenance2022}                     & lib. ins.                    & Needs more time            \\
OPUS \cite{balakrishnanOPUSLightweightSystem2013}                  & lib. ins.                    & Not reproducible           \\
CamFlow \cite{pasquierPracticalWholesystemProvenance2017}          & kernel ins.                  & Requires custom kernel     \\
Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}                   & kernel ins.                  & Requires custom kernel     \\
LPM/ProvMon \cite{batesTrustworthyWholeSystemProvenance2015}       & kernel ins.                  & Requires custom kernel     \\
Arnold\cite{devecseryEideticSystems2014}                           & kern ins.                    & Requires custom kernel     \\
LPS \cite{daiLightweightProvenanceService2017}                     & kern ins.                    & Requires custom kernel     \\
RecProv \cite{jiRecProvProvenanceAwareUser2016}                    & tracing                      & No source                  \\
FiPS \cite{sultanaFileProvenanceSystem2013}                        & FS                           & No source                  \\
Namiki et al. \cite{namikiMethodConstructingResearch2023}          & audit                        & No source                  \\
LPROV \cite{wangLprovPracticalLibraryaware2018}                    & kernel mod., lib. ins.       & No source                  \\
S2Logger \cite{suenS2LoggerEndtoEndData2013}                       & kernel mod.                  & No source                  \\
ProTracer \cite{maProTracerPracticalProvenance2016}                & kernel mod.                  & No source                  \\
PANDDE \cite{fadolalkarimPANDDEProvenancebasedANomaly2016}         & kernel ins., FS              & No source                  \\
PASS/Pasta \cite{muniswamy-reddyProvenanceAwareStorageSystems2006} & kernel ins., FS, lib. ins.   & No source                  \\
PASSv2/Lasagna \cite{muniswamy-reddyLayeringProvenanceSystems2009} & kernel ins.                  & No source                  \\
Lineage FS \cite{sarLineageFileSystem}                             & kernel ins.                  & No source                  \\
RTAG \cite{jiEnablingRefinableCrossHost2018}                       & bin. ins.                    & No source                  \\
BEEP \cite{leeHighAccuracyAttack2017}                              & bin. ins.                    & Requires HW                \\
libdft \cite{kemerlisLibdftPracticalDynamic2012}                   & bin., kernel, lib. ins.      & Requires HW                \\
RAIN \cite{jiRAINRefinableAttack2017}                              & bin. ins.                    & Requires HW                \\
DataTracker \cite{stamatogiannakisLookingBlackBoxCapturing2015}    & compile-time ins.            & Requires HW                \\
MPI\cite{maMPIMultiplePerspective2017}                             & compile-time ins.            & Requires recompilation     \\
LDX \cite{kwonLDXCausalityInference2016}                           & VM ins.                      & Requires recompilation     \\
Panorama \cite{yinPanoramaCapturingSystemwide2007}                 & VM ins.                      & VMs are too slow           \\
PROV-Tracer \cite{stamatogiannakisDecouplingProvenanceCapture2015} & audit                        & VMs are too slow           \\
ETW \cite{EventTracingWin322021}                                   & audit                        & Not for Linux              \\
Sysmon \cite{markrussSysmonSysinternals2023}                       & audit                        & Not for Linux              \\
TREC \cite{vahdatTransparentResultCaching1998}                     & tracing                      & Not for Linux              \\
URSprung \cite{rupprechtImprovingReproducibilityData2020}          & audit                        & Not for Linux\footnotemark \\
Ma et al. \cite{maAccurateLowCost2015}                             & audit                        & Not for Linux              \\
ULTra \cite{burtonWorkloadCharacterizationUsing1998}               & tracing                      & Not for Linux              \\
\bottomrule
\end{tabular}
\normalsize
\end{center}
%\end{minipage}
\end{table}
\footnotetext{URSprung depends on IBM Spectrum Scale to get directory change notifications, so it is not for a \textit{generic} Linux system.}

<!--
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

: Excluded tools. {#tbl:excluded}
-->

## Implemented Benchmarks

Of these, @Tbl:prior-benchmarks shows the benchmarks used to evaluate each tool, of which there are quite a few.
We prioritized implementing frequently-used benchmarks, easy-to-implement benchmarks, and benchmarks that have value in representing a computational science use-case.

\begin{table}
\caption{
  Benchmarks implemented by this work. For brevity, we consider categories of benchmarks in \Cref{tbl:prior-benchmarks}.
  See \Cref{benchmark-descriptions} for a description of each benchmark group and how we implemented them.
}
\label{tbl:implemented-benchmarks}
%\begin{minipage}{\columnwidth}
\begin{center}
\footnotesize
\begin{tabular}{p{0.03\textwidth}p{0.03\textwidth}p{0.032\textwidth}p{0.31\textwidth}}
\toprule
Prior works & This work & Instances     & Benchmark group and examples from prior work                                                                   \\
\midrule
12          & yes       & 5             & HTTP server/traffic                                                                                            \\
10          & yes       & 2             & HTTP server/client                                                                                             \\
10          & yes       & 8             & Compile user packages                                                                                          \\
9           & yes       & 19 + 1        & I/O microbenchmarks (lmbench + Postmark)                                                                       \\
9           & no        &               & Browsers                                                                                                       \\
6           & yes       & 3             & FTP client                                                                                                     \\
5           & yes       & 1             & FTP server/traffic                                                                                             \\
5           & yes       & $5 \times 2$  & Un/archive                                                                                                     \\
5           & yes       & 5             & BLAST                                                                                                          \\
5           & yes       & 10            & CPU benchmarks (SPLASH-3)                                                                                      \\
5           & yes       & 8             & Coreutils and system utils                                                                                     \\
3           & yes       & 2             & cp                                                                                                             \\
2           & yes       & 2             & VCS checkouts                                                                                                  \\
2           & no        &               & Sendmail                                                                                                       \\
2           & no        &               & Machine learning workflows (CleanML, Spark, ImageML)                                                           \\
1           & no        &               & Data processing workflows (VIC, FIE)                                                                           \\
1           & no        &               & benchmarks occurring in only one prior work (RUBiS, x64, mysqld, gocr, Memcache, Redis, php, pybench, ping, mp3info, ngircd, CUPS) \\
\bottomrule
\end{tabular}
\end{center}
\end{table}

@Tbl:benchmark-results shows the aggregated performance of our implemented benchmarks in our implemented provenance collectors.
From this, we observe:

- Although SPLASH-3 CPU-oriented benchmarks contain mostly CPU-bound tasks, they often need to load data from a file, which does invoke the I/O subsystem.
  They are CPU benchmarks when the CPU is changed and the I/O subsystem remains constant, but when the CPU is constant and the I/O subsystem is changed, the total running time is influenced by I/O-related overhead.

- `cp` is the slowest benchmark.
  It even induces a 45% overhead on fsatrace.

\begin{table}
\caption{
  The percent overhead of the mean walltime when running with a provenance collector versus running without provenance.
  A value of 3 means the execution in that cell takes 1.03 times the execution without provenance.
  Negative slowdown can occur sometimes due to random statistical noise.
  We aggregate values across iterations and benchmark cases (each cell) and across benchmark classes (last row) using geometric mean.
}
\label{tbl:benchmark-results}
\begin{center}
\footnotesize
%%%%%%%%% generated from script
\begin{tabular}{lllllll}
\toprule
                      & (none) & fsatrace & CARE & strace & RR   & ReproZip \\
\midrule
BLAST                 & 0      & 0        & 2    & 2      & 93   & 8        \\
CPU bench SPLASH-3    & 0      & 5        & 9    & 16     & 49   & 75       \\
Compile w/Spack       & 0      & -1       & 119  & 111    & 562  & 359      \\
Compile w/gcc         & 0      & 4        & 136  & 206    & 321  & 344      \\
Compile w/latex       & 0      & 7        & 72   & 40     & 23   & 288      \\
Data science Notebook & 0      & 4        & 15   & 32     & 20   & 174      \\
Data science python   & 0      & 5        & 85   & 84     & 150  & 346      \\
FTP srv/client        & 0      & 1        & 2    & 4      & 5    & 18       \\
HTTP srv/client       & 0      & -23      & 20   & 33     & 165  & 248      \\
HTTP srv/traffic      & 0      & 5        & 135  & 414    & 1261 & 724      \\
IO bench lmbench      & 0      & -10      & 1    & 3      & 11   & 36       \\
IO bench postmark     & 0      & 2        & 231  & 650    & 259  & 1733     \\
Tar Archive           & 0      & -0       & 75   & 113    & 179  & 140      \\
Tar Unarchive         & 0      & 4        & 44   & 114    & 195  & 149      \\
Utils                 & 0      & 17       & 118  & 280    & 1378 & 697      \\
Utils bash            & 0      & 5        & 75   & 20     & 426  & 2933     \\
VCS checkout          & 0      & 5        & 71   & 160    & 177  & 428      \\
cp                    & 0      & 37       & 641  & 380    & 232  & 5791     \\
\midrule
Total (gmean)         & 0      & 0        & 45   & 66     & 146  & 193      \\
\bottomrule
\end{tabular}
%%%%%%%%%
\normalsize
\end{center}
\end{table}

## Subsetted Benchmarks

\begin{figure*}
\subcaptionbox{
  Subsetting algorithms scored by the RMSE of the distance of each benchmark to the nearest selected benchmark.
  A dotted line shows the x- amd y-value of the point of diminishing return.
}{
  \includegraphics[width=0.38\textwidth]{generated/subsetting-dist.pdf}
  \label{fig:subsetting-dist}
}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Subsetting algorithms scored by the RMSE of the difference between (weighted) features of the subset and features of the original set.
  A dotted line shows the x- amd y-value of the point of diminishing return.
}{
  \includegraphics[width=0.38\textwidth]{generated/subsetting-accuracy.pdf}
  \label{fig:subsetting-accuracy}
}
\caption{Competition for best benchmark subsetting algorithm, sweeping over subset size on the x-axis.}
\label{fig:subsetting}
\end{figure*}

@Fig:subsetting shows the performance of various algorithms on benchmark subsetting.
We observe:

1. The features are already standardized, so PCA has little to offer besides rotation and truncation.
   However, the truncation is throwing away potentially valuable data.
   Since we have a large number of benchmarks, and the space of benchmarks is open-ended, the additional dimensions that PCA trims off appear to be important for separating clusters of data.

2. K-means and agglomerative clustering yield nearly the same results.
   They both attempt to minimize within-cluster variance, although by different methods.

3. RMSE of the residual of linear regression will eventually hit zero because the $k$ exceeds the rank of the matrix of features by benchmarks;
   Linear regression has enough degrees of freedom to perfectly map the inputs to their respective outputs.

It seems that agglomerative clustering with $k=14$ has performs quite well, and further increases in $k$ exhibit diminishing returns.
At that point, the RMSE of the linear regression is about 0.02.
Assuming the error is iid and normally distributed, we can estimate the standard error of the approximation of the total benchmark by linear regression is about 0.02 (log-space) or $e^{0.02} \approx 1.02$ (real-space).
Within the sample, 68% of the data falls within one standard error (either multiplied or divided by a factor of 1.02) and 95% of the data falls within two standard errors ( $e^{2 \cdot 0.02}$ or 1.04x).
We examine the generated clusters and benchmark subset in @Fig:dendrogram and  @Tbl:members.

\begin{figure*}
\subcaptionbox{
  Benchmark subset, where color shows resulting clusters.
  The same-color small dots are benchmarks in the same cluster, the ``x'' of that color is their hypothetical benchmark with their average features, and the big dot of that color is the closest actual benchmark to the average of their features.
  A benchmark subset replaces each cluster of small dots with just the single big dot.
  \label{fig:benchmark-clusters}
}{
  \includegraphics[width=0.45\textwidth]{generated/pca0.pdf}
}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Benchmark subset, where color shows benchmark class (see \Cref{tbl:implemented-benchmarks}).
  For example, archive-with-gzip and archive-with-bzip2 are two benchmarks of the same type, and therefore color.
  The ``x'' still shows a posteriori cluster centers as in \Cref{fig:benchmark-clusters}.
  \label{fig:benchmark-groups}
}{
  \includegraphics[width=0.45\textwidth]{generated/pca1.pdf}
}
\caption{
  Benchmarks, clustered agglomeratively into 20 subsets using standardized performance features. 
  These axes show only two dimensions of a high-dimensional space. We apply PCA \emph{after} computing the clusters, in order to project the data into a 2D plane.
}
\label{fig:benchmark}
\end{figure*}

@Fig:benchmark-clusters 
shows the a posteriori clusters with colors.
@Fig:benchmark-groups shows a priori benchmark "types", similar but more precise than those in @Tbl:implemented-benchmarks.
From these two, we offer the following observations:

1. It may appear that the algorithm did not select the benchmark closest to the cluster center, but this is because we are viewing a 2D projection of a high-dimensional space, like how three stars may appear next to each other in the sky but in reality, one pair may be much closer than the other, since we cannot perceive the radial distance to each star.

2. Many clusters are singletons, e.g., `simplhttp` near $(4,6)$; this is surprising, but given there are no points nearby, that decision seems reasonable.

3. We might expect that benchmarks of the same type would occupy nearby points in PCA space, but they often do not.
  lmbench is particularly scattered with points at $(-2, 0)$ and $(0, 5)$, perhaps because it is a microbenchmark suite where each microbenchmark program tests a different subsystem.

4. Postmark is intended to simulate the file system traffic of a web server (many small file I/O).
   Indeed the Postmark at $(3.5, -2)$ falls near several of the HTTP servers at $(6, -3)$ and $(7, -3)$.
   Copy is also similar.

\begin{figure}
\begin{center}
\includegraphics[width=0.38\textwidth]{generated/dendrogram.pdf}
\caption{
  Dendrogram showing the distance between clusters.
  A fork at $x = x_0$ indicates that below that threshold of within-cluster variance, the two children clsuters are far away enough that they should be split into two; conversely, above that threshold they are close enough to be combined.
}
\label{fig:dendrogram}
\end{center}
\end{figure}

\begin{table}
\begin{center}
\footnotesize
\begin{tabular}{l p{0.4\textwidth}}
\toprule
  & \textbf{Representative} \\
  & Members \\
%%%%%%%%%%%%%%%% generated
\midrule
 54.7 & \textbf{CPU bench SPLASH-3 (nsquared)}                                                            \\
     & BLAST  (all), CPU bench SPLASH-3 (ocean, lu, cholesky, radiosity, spatial, volrend, radix, raytrace), Compile w/latex (all), Data science Notebook (all), FTP srv/client (all), HTTP srv/client (all), HTTP srv/traffic (minihttp), IO bench lmbench (write, select-file, mmap, catch-signal, protection-fault, getppid, install-signal, page-fault, fs, bw\_unix, select-tcp, bw\_file\_rd, bw\_pipe, read), Tar Archive (gzip, bzip2), Tar Unarchive (bzip2) \\
 12.7 & \textbf{IO bench postmark (main)}                                                                 \\
     & Tar Archive (archive), cp  (all)                                                                  \\
 7.7 & \textbf{Tar Unarchive (pbzip2)}                                                                   \\
     & HTTP srv/traffic (lighttpd), Tar Archive (pigz, pbzip2)                                           \\
 5.8 & \textbf{Compile w/Spack (python)}                                                                 \\
     & Compile w/Spack (rest)                                                                            \\
 5.4 & \textbf{Utils  (hello)}                                                                           \\
     & Utils  (rest)                                                                                     \\
 3.7 & \textbf{Utils bash (shell-incr)}                                                                  \\
     & CPU bench SPLASH-3 (fft), Utils bash (shell-echo)                                                 \\
 1.6 & \textbf{Utils bash (cd)}                                                                          \\
 1.4 & \textbf{IO bench lmbench (exec)}                                                                  \\
 1.4 & \textbf{HTTP srv/traffic (nginx)}                                                                 \\
 1.3 & \textbf{IO bench lmbench (open/close)}                                                            \\
 1.2 & \textbf{HTTP srv/traffic (simplehttp)}                                                            \\
 1.0 & \textbf{IO bench lmbench (fork)}                                                                  \\
 0.2 & \textbf{HTTP srv/traffic (apache)}                                                                \\
 0.0 & \textbf{Tar Unarchive (pigz)}                                                                     \\
     & Compile w/gcc (all), Data science python (all), IO bench lmbench (stat, fstat), Tar Unarchive (gzip, unarchive), VCS checkout  (all) \\
\midrule
98.1 & \textbf{Sum} \\
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
\bottomrule
\end{tabular}
\normalsize
\caption{
  A table showing cluster membership and weights as percentages.
  The weights show one way of approximating the features in the original set, which is by multiplying the features of the cluster representative by the weight and summing over all clusters.
}
\label{tbl:members}
\end{center}
\end{table}

To elucidate the structure of the clusters, we plotted a dendrogram (@Fig:dendrogram) and listed the members of each cluster (@Tbl:members).
We offer the following observations:

1. lmbench fork and lmbenhc exec are close in feature-space, probably because programs usually do both.

2. Utilities (especially GNU hello, which prints hello and exits) terminate very quickly, so they probably measure resources used to load and exit a program.
   We run these commands in a loop hundreds or thousands of times, so the runtime is more accurately measurable.
   cd and shell-increment, on the other hand, are shell builtins, so they do not even need to load a program.
   That cluster probably represents purely CPU-bound workloads.

3. Many of the CPU-heavy workloads are grouped together under lm-protection-fault.

4. Many of the un/archive benchmarks are grouped together with lighttpd, which also accesses many files.

### Our suggested subset

- Running a CPU heavy benchmark (**from the 55% cluster** in @Tbl:members) is important, in some sense.
  It has the heaviest weight because more of the selected programs are similar.
  This weighting will change with the domain, but it holds on our sample of programs.

- The programs in **lmbench** have very different performance characteristics (see @Fig:benchmark-groups).
  Due to their simplicity, their results are interpretable (e.g., testing latency of `open()` followed by `close()` in a tight loop).
  We report the total time it takes to run a large number of iterations[^lmbench-usage] rather than latency or throughput to be consistent with benchmarks for which latency and throughput are not applicable.
  If one has to run part of lmbench, it is not too hard to run all of lmbench.

  [^lmbench-usage]: Users should set the environment variable `ENOUGH` to a large integer. Otherwise, lmbench will choose a number of iterations based on the observed speed of the machine, which can vary between runs.

- @Fig:benchmark-groups shows that **HTTP servers are very "unique"**.
  Three of five were selected as cluster centers, and we can tell from @Fig:benchmark-clusters they are quite far from other programs in feature-space.
  This "uniqueness" means that future work interested in representativeness and consistency with prior work should include HTTP servers, but future     work not on security may be able to do without them.
  In that case, they should run **Postmark** instead, which is intended to mimic the workload of a webserver, and according to @Fig:benchmark, will pull the benchmarks the direction of Nginx and ApacheHttpd.

- Surprisingly, **shell builtins** and **Linux utilities** in a tight loop exercise provenance collectors well according to @Tbl:benchmark-results, probably due to their fast execution time compared to the fixed cost of loading a program and its libraries into memory.
  At least they are easy to run.

There is an old adage, \emph{the best benchmark is always the target application}.
Benchmarking lmbench reveals certain aspects of performance, but benchmarking the target application reveals the _actual_ performance.
If we may hazard a corollary, we might say, \emph{the second best benchmark is one from the target domain}.
Supposing one does not know the exact application or inputs their audience will use, selecting applications from that domain is the next best option.
Future work on system-level provenance for computational science should, of course, use a computational science benchmark, such as BLAST, compiling programs with Spack, or a workflow, whether or not they are selected by this clustering analysis.
Likewise, work on security should include HTTP servers.

Finally, researchers presenting new provenance collectors should report _all_ benchmark runtimes, not just a geometric mean [@masheyWarBenchmarkMeans2004].
Readers can be the ones to determine weights for which benchmarks are most relevant to their workload.
<!-- TODO: We should do that -->

# Discussion

**Prior work focuses on security, not computational science.**
@Tbl:implemented-benchmarks shows the top-used benchmarks are server programs, followed by I/O benchmarks.
Server programs access many small files with concurrency, which is a different file-access pattern than scientific applications.
BLAST (used by 5 / 29 publications with benchmarks; see @Tbl:prior-benchmarks) is the only scientific program to be used as a benchmark by more than one publication.

One difference between security and computational science is that security-oriented provenance collectors have to work with adversarial programs:
there should be no way for the program to circumvent the provenance tracing, e.g. `PTRACE_DETACH`.
Computational science, on the other hand, may satisfied by a solution that *can* be intentionally circumvented by an uncooperative program but would work most of the time.
Other computational science tools use circumventable methods without mention [@xuDXTDarshanEXtended2017].

<!--
**Prior work on provenance collectors doesn't test on many workflows.**
Workflows, for the purposes of this discussion, are programs that are structured as a set of loosely coupled components whose execution order is determined by dataflow.
Workflows are important for computational science, but also other domains, e.g., online analytical processing (also known as OLAP).
Under this definition, non-trivial source-code compilation is a workflow.
-->

**Provenance collectors vary in power and speed, but fast-and-powerful could be possible.**
While all bear the title provenance collector, some are **monitoring**, merely recording a history of operations, while others are **interrupting**, interrupt the process when the program makes an operation.
Fsatrace, Strace, and Ltrace are monitoring, while ReproZip, Sciunit, RR, CARE, and CDE are interrupting, using their interruption store a copy of the files that would be read or appended to by the process.
None of the interrupting provenance collectors we tested use library interposition or eBPF (although PROV-IO does, we did not have time to implement it).
Perhaps a faster underlying method would allow powerful features of interrupting collectors in a reasonable overhead budget.

**Current provenance collectors are too slow for "always on".**
One point of friction when using system-level provenance collection is that users have to remember to turn it on, or else the system is useless.
An "always on" provenance system could alleviate that problem; for example, a user might change their login shell to start within a provenance collector.
Unfortunately, the conventional provenance collectors exhibit an intolerably high overhead to be always used, with the exception of fsatrace.
fsatrace is able to so much faster because it uses library interpositioning rather than ptrace (see "fast-and-powerful" discussion above), but fsatrace is one of the weakest collectors; it only collects file reads, writes, moves, deletes, queries, and touches (nothing on process forks and execs).

**The space of benchmark performance in provenance systems is highly dimensional.**
The space of benchmarks is naturally embedded in a space with features as dimensions.
If there were many linear relations between the features (e.g., slowdown = (app syscalls / sec) * (prov syscall latency)), then we would expect clustering to reveal fewer clusters than the number of features.
However, there are more clusters than features (14 &gt; 12); it seems that most dimensions are not linearly redundant.
Even the relationship between workloads is non-linear; if workload A is a weighted average of B and C in feature-space (e.g., num of syscalls), its runtime is not necessarily the same weighted average of B and C's runtime.

**Computational scientists may already be using workflows.**
While system-level provenance is the easiest way to get provenance out of many applications, if the application is already written in a workflow engine, such as Pegasus [@kimProvenanceTrailsWings2008], they can get provenance through the engine.
Computational scientists may move to workflows for other reasons because they make it easier to parallelize code on big machines and integrate loosely coupled components.
That may explain why prior work on system-level provenance focuses more on security applications.

## Threats to Validity

**Internal validity**: We mitigate measurement noise by:

- Isolating the sample machine \Cref{performance-experiment}
- Running the code in cgroups with a fixed allocation of CPU and RAM
- Rewriting benchmarks that depend on internet resources to only depend on local resources
- Averaging over 3 iterations helps mitigate noise.
- Randomizing the order of each pair of collector and benchmark within each iteration.

**External validity**:
When measuring the representativeness of our benchmark subset, we use other workload characteristics, not just performance in each collector.
Therefore, our set also maintains variety and representativeness in underlying characteristics, not just in the performance we observe.
Rather than select the highest cluster value, we select the point of diminishing return, which is more likely to be generalizable.

## Future Work

In the future, we plan to implement compilation for more packages, particularly xSDK [@bartlettXSDKFoundationsExtremescale2017] packages.
Compilation for these packages may differ from ApacheHttpd and Linux because xSDK is organized into many dozens of loosely related packages.
We also plan to implement computational workflows.
Workflows likely have a different syscall access pattern, unlike HTTP servers because the files may be quite large, unlike `cp` because workflows have CPU work blocked by I/O work, and unlike archiving because there are multiple "stages" to the computation.

We encourage future work that implements an interrupting provenance collector using faster methods like library interposition or eBPF instead of `ptrace`.
Between them, there are pros and cons: eBPF requires privileges but could be exposed securely by a setuid/setgid binary; library interposition assumes the tracee only uses libc to make I/O operations.
Another optimization postponing work to off the critical path:
if a file is read, it can be copied at any time unless/until it gets mutated ("copy-on-write-after-read").
Other reads can be safely copied after the program is done, and new file writes obviously do not need to be copied at all.
Perhaps the performance overhead would be low enough to be "always on", however storage and querying cost need to be dispatched with as well.

# Conclusion

We intend this work to bridge research to practical use of provenance collectors and an invitation for future research.
In order to bridge research into practice, we identified reproducible and usable provenance collectors from prior work and evaluated their performance on synthetic and real-world workloads.
In order to invite future research, we collated and minimized a benchmark suite and identified gaps in prior work.
We believe this work and the work it enables will address the practical concerns of a user wanting to use a provenance collector.

\begin{acks}
This work was partially supported by NSF grants CCF-1763788 and CCF-1956374.
We acknowledge support for research on flaky tests from Google and Meta.
\end{acks}

\appendix

# Apendices

## Notable provenance collectors

**CDE** is a record/replay tool proposed by Guo and Engler [@guoCDEUsingSystem2011].
During record, CDE  uses `ptrace` to intercept its syscalls, and copy relevant files into an archive.
During rerun, can use `ptrace` to intercept syscalls and redirect them to files in the archive.
PTU uses a modified version of CDE that works on all of our benchmarks, so we can use that as a proxy.

**ltrace** similar to strace, but it traces dynamic library calls not necessarily syscalls.
It still uses `ptrace`.

**strace** is a well-known system program that uses Linux's `ptrace` functionality to record syscalls, their arguments, and their return code to a file.
strace even parses datastructures to write strings and arrays rather than pointers.
In this work, we use an strace configuration that captures all file-related syscalls but read/write[^read/write], file-metadata realated syscalls, socket- and IPC- related sycalls but send/recv, and process-related syscalls.

[^read/write]: We do not need to capture individual reads and writes, so long as we capture that the file was opened for reading/writing.

**fsatrace** reports file I/O using library-interpositioning, a technique where a program mimics the API of a standard library.
Programs are written to call into the standard library, but the loader sends those calls to the interpositioning library instead.
The interpositioning library can log the call and pass it to another library (possibly the "real" one), so the program's functionality is preserved.
This avoids some context-switching overhead of `ptrace`, since the logging happens in the tracee's process.

**CARE** is a record/replay tool inspired by CDE.
However, CARE has optimizations enabling it to copy fewer files, and CARE archives can be replayed using `chroot`, `lxc`, or `ptrace` (by emulating `chroot`); CDE only supports `ptrace`, which is slower than the other two.

**RR** [@ocallahanEngineeringRecordReplay2017] is a record/replay tool.
It captures more syscalls than just file I/O, including `getrandom` and `clock_gettime` and it is able to replay its recordings in a debugger.
Where other record/replay tools try to identify the relevant files, RR only memorizes the responses to each syscall, so it can only replay that exact code path.
CDE, CARE, ReproZip, PTU, and Sciunit allow one to replay a different binary or supply different inputs in the filesystem of an existing recording.

**ReproZip** is a record/replay inspired by CDE.
ReproZip archives can be replayed in Vagrant, Docker, Chroot, or natively.
Unlike other record/replay tools, ReproZip explicitly constructs the computational provenance graph.

**PTU** (Provenance-To-Use) is an adaptation of CDE which explicitly constructs the computational provenance graph.

**Sciunit** is a wrapper around PTU that also applies block-based deduplication.

## Collection methods

**User-level tracing**:
A provenance tool may use "debugging" or "tracing" features provided by the kernel, e.g., `ptrace(2)` [@Ptrace], to trace another program's I/O operations.

**Built-in auditing service**:
A provenance tool may use auditing service built in to the kernel, e.g., Linux Auditing Framework [@madabhushanaConfigureLinuxSystem2021], enhanced Berkeley Packet Filter (eBPF) [@BPFDocumentation], kprobes [@kenistonKernelProbesKprobes], and ETW [@EventTracingWin322021] for Windows.

**Filesystem instrumentation**:
A provenance tool may set up a file system, so it can log I/O operations, e.g., using Filesystem in User SpacE (FUSE) interface [@FUSE], or Virtual File System (VFS) interface [@goochOverviewLinuxVirtual].

**Dynamic library instrumentation**:
A provenance tool may replace a library used to execute I/O operations (e.g., glibc) with one that logs the calls before executing them.

**Binary instrumentation**:
A provenance tool may use binary instrumentation (dynamic or static) to identify I/O operations in another program.

**Compile-time instrumentation**:
A provenance tool may be a compiler pass that modifies the program to emit provenance data, especially intra-program control flow.

**Kernel instrumentation**:
A provenance tool may be a modified kernel either by directly modifying and recompiling the kernel's source tree.

**Kernel module**:
Rather than directly modify the kernel's source, the provenance tool may simply require that the user load a custom kernel module.

**VM instrumentation**:
A provenance tool may execute the program in a virtual machine, where it can observe the program's I/O operations.

See @Tbl:prior-benchmarks for a list of prior publications and what benchmarks they use, if, for example, one wishes to see the original contexts in which Firefox was used.

\begin{table}[h]
\caption{Benchmarks used by prior works on provenance collectors (sorted by year of publication).}
\label{tbl:prior-benchmarks}
\begin{center}
\scriptsize
\begin{tabular}{p{0.10\textwidth}p{0.27\textwidth}p{0.06\textwidth}}
\toprule
Publication                                                  & Benchmarks                                                                                                                                      & Comparisons           \\
\midrule
TREC \cite{vahdatTransparentResultCaching1998}               & open/close, compile Apache, LaTeX                                                                                                               & Native                \\
ULTra \cite{burtonWorkloadCharacterizationUsing1998}         & getpid, LaTeX, Apache, compile package                                                                                                          & Native, strace        \\
PASS \cite{muniswamy-reddyProvenanceAwareStorageSystems2006} & BLAST                                                                                                                                           & Native ext2           \\
Panorama \cite{yinPanoramaCapturingSystemwide2007}           & curl, scp, gzip, bzip2                                                                                                                          & Native                \\
PASSv2 \cite{muniswamy-reddyLayeringProvenanceSystems2009}   & BLAST, compile Linux, Postmark, Mercurial, Kepler                                                                                               & Native ext3, NFS      \\
SPADEv2 \cite{gehaniSPADESupportProvenance2012}              & BLAST, compile Apache, Apache                                                                                                                   & Native                \\
Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}             & lmbench, compile Linux, Postmark                                                                                                                & Native                \\
libdft \cite{kemerlisLibdftPracticalDynamic2012}             & scp, \{tar, gzip, bzip2\} x \{extract, compress\}                                                                                               & PIN                   \\
PTU \cite{phamUsingProvenanceRepeatability2013}              & Workflows (PEEL0, TextAnalyzer)                                                                                                                 & Native                \\
LogGC \cite{leeLogGCGarbageCollecting2013}                   & RUBiS, Firefox, MC, Pidgin, Pine, Proftpd, Sendmail, sshd, vim, w3m, wget, xpdf, yafc, Audacious, bash, Apache, mysqld                          & None\footnotemark     \\
CARE \cite{janinCAREComprehensiveArchiver2014}               & Compile perl, xz                                                                                                                                & Native                \\
Arnold\cite{devecseryEideticSystems2014}                     & cp, CVS checkout, make libelf, LaTeX, Apache, gedit, Firefox, spreadsheet, SPLASH-2                                                             & Native                \\
LPM/ProvMon \cite{batesTrustworthyWholeSystemProvenance2015} & lmbench, compile Linux, Postmark, BLAST                                                                                                         & Native                \\
Ma et al. \cite{maAccurateLowCost2015}                       & TextTransfer, Chromium, DrawTool, NetFTP, AdvancedFTP, Apache, IE, Paint, Notepad, Notepad++, simplehttp, Sublime Text                          & Native                \\
ProTracer \cite{maProTracerPracticalProvenance2016}          & Apache, miniHTTP, ProFTPD, Vim, Firefox, w3m, wget, mplayer, Pine, xpdf, MC, yafc                                                               & Auditd, BEEP          \\
LDX \cite{kwonLDXCausalityInference2016}                     & SPEC CPU 2006, Firefox, lynx, nginx, tnftp, sysstat, gif2png, mp3info, prozilla, yopsweb, ngircd, gocr, Apache, pbzip2, pigz, axel, x264        & Native                \\
PANDDE \cite{fadolalkarimPANDDEProvenancebasedANomaly2016}   & ls, cp, cd, lpr                                                                                                                                 & Native                \\
MPI \cite{maMPIMultiplePerspective2017}                      & Apache, bash, Evince, Firefox, Krusader, wget, most, MC, mplayer, MPV, nano, Pine, ProFTPd, SKOD, TinyHTTPd, Transmission, Vim, w3m, xpdf, Yafc & Audit, LPM-HiFi       \\
CamFlow \cite{pasquierPracticalWholesystemProvenance2017}    & lmbench, postmark, unpack kernel, compile Linux, Apache, Memcache, redis, php, pybench                                                          & Native                \\
BEEP \cite{leeHighAccuracyAttack2017}                        & Apache, Vim, Firefox, wget, Cherokee, w3m, ProFTPd, yafc, Transmission, Pine, bash, mc, sshd, sendmail                                          & Native                \\
RAIN \cite{jiRAINRefinableAttack2017}                        & SPEC CPU 2006, cp linux, wget, compile libc, Firefox, SPLASH-3                                                                                  & Native                \\
Sciunit \cite{tonthatSciunitsReusableResearch2017}           & Workflows (VIC, FIE)                                                                                                                            & Native                \\
LPS \cite{daiLightweightProvenanceService2017}               & IOR benchmark, read/write, MDTest, HPCG                                                                                                         & Native                \\
LPROV \cite{wangLprovPracticalLibraryaware2018}              & Apache, simplehttp, proftpd, sshd, firefox, filezilla, lynx, links, w3m, wget, ssh, pine, vim, emacs, xpdf                                      & Native                \\
MCI \cite{kwonMCIModelingbasedCausality2018}                 & Firefox, Apache, Lighttpd, nginx, ProFTPd, CUPS, vim, elinks, alpine, zip, transmission, lftp, yafc, wget, ping, procps                         & BEEP                  \\
RTAG \cite{jiEnablingRefinableCrossHost2018}                 & SPEC CPU 2006, scp, wget, compile llvm, Apache                                                                                                  & RAIN                  \\
URSPRING \cite{rupprechtImprovingReproducibilityData2020}    & open/close, fork/exec/exit, pipe/dup/close, socket/connect, CleanML, Vanderbilt, Spark, ImageML                                                 & Native, SPADE         \\
PROV-IO \cite{hanPROVIOOCentricProvenance2022}               & Workflows (Top Reco, DASSA), I/O microbenchmark (H5bench)                                                                                                            & Native                \\
Namiki et al. \cite{namikiMethodConstructingResearch2023}    & I/O microbenchmark (BT-IO)                                                                                                                                  & Native                \\
\bottomrule
\normalsize
\end{tabular}
\end{center}
\end{table}
\footnotetext{LogGC measures the offline running time and size of garbage collected logs; there is no comparison to native would be applicable.}
