---
from: markdown
verbosity: INFO
citeproc: yes
ccite-method: citeproc
bibliography:
  - zotero
  - reed
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
  - name: Daniel S. Katz
    orcid: 0000-0001-5934-7525
    email: dskatz@illinois.edu
    affiliation:
      institution: University of Illinois Urbana-Champaign
      department:
        - NCSA & CS & ECE & iSchool
      streetaddress:  1205 W Clark St
      city: Urbana
      state: IL
      country: USA
      postcode: 61801
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
  - authordraft=true
  - timestamp=true
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
---

# Introduction

Within the computational science and engineering (CSE) community, there is a consensus that greater reproducibility is a pathway towards increased productivity and more impactful science [@nasem2019report].
In the past decade, this has inspired a diverse range of research and development efforts meant to give us greater control over our software, including containers and virtual machines to capture environments [@boettiger2015introduction; @nust2020ten; @jansen2020curious; @satyanarayanan2023towards], package managers for fine-grained management of dependencies [@gamblin2015spack; @kowalewski2022sustainable], interactive notebooks and workflows [@beg2021using; @di2017nextflow; @koster2012snakemake], and online platforms for archiving and sharing computational experiments [@goecks2010galaxy; @stodden2012runmycode; @stodden2015researchcompendia; @chard2019implementing].
In this work, we focus our attention on **computational provenance** as another complementary strategy for managing reproducibility across the research software lifecycle.
Computational provenance is the history of a computational task, describing the artifacts and processes that led to or influenced the end result [@freireProvenanceComputationalTasks2008]; the term encompasses a spectrum of tools and techniques ranging from simple logging to complex graphs decorated with sufficient detail to replay a computational experiment.

Provenance data can provide crucial information about the hardware and software environments in which a code is executed. The use cases for this data are numerous, and many different tools for collecting it have independently developed. What has been lacking, however, is a rigorous comparison of those available tools and the extent to which they are practically usable in CSE application contexts^[DSK: usable globally or perhaps in particular situations?]. In an effort to summarize the state of the art and to establish goalposts for future research in this area, our paper makes the following contributions:

- *A rapid review on available system-level provenance collectors*.

- *A benchmark suite for system-level provenance collectors*:
  Prior work does not use a consistent set of benchmarks; often publications use an overlapping set of benchmarks from prior work.
  We collate benchmarks used in prior work, add some unrepresented areas, and find a statistically valid subset of the benchmark.

- *A quantitative performance comparison of system-level provenance collectors against this suite*:
  Prior publications often only compares the performance their provenance tool to the baseline, no-provenance performance, not to other provenance tools.
  It is difficult to compare provenance tools, given data of different benchmarks on different machines.
  We run a consistent set of benchmarks on a single machine over all provenance tools.

- *A predictive performance model for system-level provenance collectors*:
  The performance overhead of a single provenance collector varies from <1% to 23% [@muniswamy-reddyLayeringProvenanceSystems2009] than without provenance depending on the application, so a single number for overhead is not sufficient.
  We develop a statistical model for predicting the overhead of \$X application in \$Y provenance collector based on \$Y provenance collector's performance on our benchmark suite and \$X application's performance characteristics (e.g., number of I/O syscalls).
  
The remainder of the paper is structured as follows. [^RMM: Outline paper structure here.]

# Background

Provenance tools and data have many potential applications, including the following from Pimentel et al. [@pimentelSurveyCollectingManaging2019] and Sar and Cao [@sarLineageFileSystem]:

1. **Reproducibility**.
   A description of the inputs and processes used to generate a specific output can aid manual and automatic reproduction of that output[^acm-defns].
   Lack of reproducibility in computational experiments undermines the long-term credibility of science and hinders the day-to-day work of researchers.
   Empirical studies [@trisovicLargescaleStudyResearch2022; @graysonAutomaticReproductionWorkflows2023; @collbergRepeatabilityComputerSystems2016; @zhaoWhyWorkflowsBreak2012] show that reproducibility is rarely achieved in practice, probably due to its difficulty under the short time budget that scientists have available to spend on reproducibility.
   If reproducibility was easier to attain, perhaps because of automatic provenance tracking, it may improve the reproducibility rate of computational research.

   - **Manual reproducibility**.
     Provenance data improves manual reproducibility, because users have a record of the inputs, outputs, and processes used to create a computational artifact.

   - **Automatic reproducibility**.
     Provenance data also has the potential to enable automatic reproducibility, if the process trace is detailed enough to be "re-executed".
     This idea is also called "software record/replay".
     However, not all provenance collectors make this their goal.

   [^acm-defns]: "Reproduction", in the ACM sense, where a **different team** uses the **same artifacts** to generate the output artifact [@acminc.staffArtifactReviewBadging2020].

2. **Caching subsequent re-executions**.
   Computational science inquiries often involve changing some code and re-executing the workflows (e.g., testing different clustering algorithms).
   In these cases, the user has to keep track of what parts of the code they changed, and which process have to be re-executed.
   However, an automated system could read the computational provenance graphs produced by previous executions, look at what parts of the code changed, and safely decide what processes need to be re-executed.
   The dependency graph would be automatically deduced, leaving less chance for a dependency-misspecification, unlike Make and CMake, which require the user to manually specify a dependency graph.

3. **Comprehension**. 
   Provenance helps the user understand and document workflows.
   An automated tool that consumes provenance can answer queries like "What version of the data did I use for this figure?" and "Does this workflow include FERPA-protected data?".

4. **Data cataloging**.
   Provenance data can help catalog, label, and recall experimental results based on the input parameters.
   For example, a user might have run dozens of different versions of their workflow, and they may want to ask an automated system, "show me the results I previously computed based on that data with this algorithm?".

5. **Space compression**.
   If the provenance of a particular artifact is known, the artifact may be able to be deleted to save space, and regenerated when needed. Historically, as computing systems has improved, a later regeneration takes less time than the original. 

There are three high-level methods by which one can capture computational provenance: 1) by modifying an application to report provenance data, 2) by leveraging a workflow engine or programming language to report provenance data, and 3) by leveraging an operating system to emit provenance data to report provenance data [@freireProvenanceComputationalTasks2008].

- **Application-level** provenance is the most semantically rich, since it knows the use of each input at the application-level, but the least general, since each application would have to be modified individually.

- **Workflow-level** or **language-level** provenance is a middle ground in semantic richness and generality;
  it only knows the use of inputs in a dataflow sense, but all applications using the provenance-modified workflow engine or programming language would emit provenance data without themselves being modified to emit provenance data.

- **System-level** is the most general, since all applications on the system would emit provenance data, but it is the least semantically rich, since observed dependencies may overapproximate the true dependencies.

System-level provenance collectors may be implemented in **kernel-space** or in **user-space**.
Since kernel-space provenance collectors modify internals of the Linux kernel, keeping them up-to-date as the kernel changes is a significant maintenance burden.
High-security national labs may be wary of including a patched kernel.
On the other hand, user-space collectors compromise performance in exchange for requiring less maintenance and less privilege.

In the context of system-level provenance, artifacts are usually files, processes, or strings of bytes. Operations are usually syscalls involving artifacts, e.g., `fork`, `exec`, `open`, `close`.
For example, suppose a bash script runs a Python script that uses matplotlib to create a figure.
A provenance collector may record the events in @Fig:prov-example.

\begin{figure*}
\begin{center}
\subcaptionbox{
    List of events recorded by system-level provenance.
  }{
  \begin{minipage}{0.4\textwidth}
  \begin{enumerate}
    \item The user created a process, call it PID=1.
    \item The process PID=1 executed bash.
    \item The loader of process PID=1 loaded libc.so.6.
    \item The process PID=1 forked a process, call it PID=2.
    \item The process PID=2 executed python.
    \item The process PID=2 read script.py.
    \item The process PID=2 read matplotlib.py (script library).
    \item The process PID=2 opened database` for reading and writing, which creates a new version of the node in th provenance graph.
    \item The process PID=2 read data.csv.
    \item The process PID=2 wrote figure.png+.
  \end{enumerate}
  \end{minipage}
}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Graph of events recorded by system-level provenance.
  The arrows point in the direction of dataflow.
  Other authors use other conventions for what they render as nodes, edges, and arrow direction.
}{\includegraphics[width=0.45\textwidth]{prov-example.pdf}}
\label{fig:prov-example}
\end{center}
\end{figure*}

This collector could infer the required files (including executables, dynamic libraries, scripts, script libraries (e.g., matplotlib), data) *without* knowing anything about the program or programming language.
We defer to the cited works for details on versioning artifacts [@balakrishnanOPUSLightweightSystem2013] and cycles [@muniswamy-reddyProvenanceAwareStorageSystems2006].
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
}{\includegraphics[width=0.12\textwidth]{sys-lvl-log.pdf}\label{fig:sys-lvl-log}} % TODO: fix the aspect ratio here
\hspace{0.03\textwidth}%
\subcaptionbox{
  System-level provenance, inferred from the log in Fig. 1c., has the least amount of semantic information
}{\includegraphics[width=0.22\textwidth]{sys-lvl-prov.pdf}\label{fig:sys-lvl-prov}}
\caption{Several provenance graphs collected at different levels for the same application.}
\label{fig:prov}
\end{figure*}
-->

One may imagine an abstract tradeoff curve between "enabling provenance applications such as reproducibility" as the horizontal axis increasing rightwards and "cost of implementation" that provenance data on the vertical axis increasing upwards).
A typical status quo, not collecting any provenance data and not using workflows, is at the bottom left:
  no added cost and does nothing to enable provenance applications.
System-level, workflow/language-level, and application-level are on a curve, increasing cost and enabling more provenance applications.

The implementation cost in adopting system-level provenance in a project which currently has no provenance is low because the user need not change _anything_ about their application;
  they merely need to install some provenance tracer onto their system and run their code, without modifying it, in the tracer. ^[DSK: what about the performance penalty? Since you talk about performance in contributions, I think you have to introduce it here. SAG: This is referring to the "cost of switching from no-prov to prov", which is low, and I'm only using this argument to explain why I look at system-level over the others. Performance overhead between system-level tools is a concern that I will address later on. DSK: maybe add a word ("implementation"?) before cost to say which cost is meant here?]
Perceived ease of use is a critical factor in the adoption of new technologies (formalized in the Technology Acceptance Model [@davisTechnologyAcceptanceModel1985]).
Although the user may eventually use more semantically rich provenance, low-initial-cost system-level provenance would get provenance's "foot in the door". 
While this data is less rich than that of the workflow or application level, it may be enough to enable important applications such as reproducibility, caching, etc.
Since system-level provenance collection is a possibly valuable tradeoff between implementation cost and enabling provenance applications, system-level provenance will be the subject of this work.

While there is little added human overhead in using system-level provenance (no user code change), there is a non-trivial implicit overhead in monitoring and recording each computational process.
Even a minor overhead per I/O operation would become significant when amplified over the tens of thousands of I/O operations that a program might execute per second.

Prior publications in system-level provenance usually contains some benchmark programs to evaluate the overhead imposed by the system-level provenance tool.
However, the set of chosen benchmark programs are not consistent from one publication to another, and overhead can be extermely sensitive to the exact choice of benchmark, so these results are totally incomparable between publications.
Most publications only benchmark their new system against native/no-provenance, so prior work cannot easily establish which system-level provenance tool is the fastest.

# Methods

## Rapid Review

We began a rapid review to identify the research state-of-the-art tools for automatic system-level provenance.

Rapid Reviews are a lighter-weight alternative to systematic literature reviews with a focus on timely feedback for decision-making.
Schünemann and Moja [@schunemannReviewsRapidRapid2015] show that Rapid Reviews can yield substantially similar results to a systematic literature review, albeit with less detail.
Although developed in medicine, Cartaxo et al. show that Rapid Reviews are useful for informing software engineering design decisions [@cartaxoRoleRapidReviews2018; @cartaxoRapidReviewsSoftware2020].

We conducted a rapid review with the following parameters:

- **Objective**: Identify system-level provenance collection tools.

- **Search terms**: "system-level AND provenance", "computational provenance"

- **Search engine**: Google Scholar

- **Number of results**: 50 of both searches

  - This threshold is the point of diminishing returns, as no new collectors came up in the 40th – 50th results.

- **Criteria**:
  A relevant publication would center on one or more operating system-level provenance collectors that capture file provenance.
  A tool requiring that the user use a specific application or platform would be irrelevant.

We record the following features for each system-level provenance tool:

- **Capture method**: What method does the tool use to capture provenance?

  - **User-level tracing**:
    A provenance tool may use "debugging" or "tracing" features provided by the kernel, e.g., `ptrace(2)` [@Ptrace], to trace another program's I/O operations.

  - **Built-in auditing service**:
    A provenance tool may use auditing service built in to the kernel, e.g., Linux Auditing Framework [@madabhushanaConfigureLinuxSystem2021], enhanced Berkeley Packet Filter (eBPF) [@BPFDocumentation], kprobes [@kenistonKernelProbesKprobes], and ETW [@EventTracingWin322021] for Windows.

  - **Filesystem instrumentation**:
    A provenance tool may set up a file system, so it can log I/O operations, e.g., using Filesystem in User SpacE (FUSE) interface [@FUSE], or Virtual File System (VFS) interface [@goochOverviewLinuxVirtual].

  - **Dynamic library instrumentation**:
    A provenance tool may replace a library used to execute I/O operations (e.g., glibc) with one that logs the calls before executing them.

  - **Binary instrumentation**:
    A provenance tool may use binary instrumentation (dynamic or static) to identify I/O operations in another program.

  - **Compile-time instrumentation**:
    A provenance tool may be a compiler pass that modifies the program to emit provenance data, especially intra-program control flow.

  - **Kernel instrumentation**:
    A provenance tool may be a modified kernel either by directly modifying and recompiling the kernel's source tree.

  - **Kernel module**:
    Rather than directly modify the kernel's source, the provenance tool may simply require that the user load a custom kernel module.

  - **VM instrumentation**:
    A provenance tool may execute the program in a virtual machine, where it can observe the program's I/O operations.

<!--
- **Is source code available?**:
  We use the categorical codes given by Collberg and Proebsting [@collbergRepeatabilityComputerSystems2016] to describe whether the source code is in the article, found on the web, found by an email from the author, refused from an email by the author, or the authors did not reply.
-->

## Benchmark Selection

Using the tools selected above, we identified all benchmarks that have been used in prior work.
We excluded benchmarks for which we could not even find the original program (e.g., TextTransfer), benchmarks that were not available for Linux (e.g., Internet Explorer), benchmarks with a graphical component (e.g., Notepad++), or benchmarks with an interactive component (e.g., GNU Midnight Commander).

We implemented the benchmarks as packages for the Nix package manager^[See https://nixos.org/guides/how-nix-works], so they are runnable on many different platforms.
Nix has official installers for Linux, Mac OS X, and Windows Subsystem for Linux on i686, x86_64, and aarch64 architectures, but FreeBSD and OpenBSD both package Nix themselves, and it can likely be built from source on even more platforms.

We also added new benchmarks:

<!--
- **Workflows**:
  Only one of the commonly used benchmarks from prior work (BLAST) resembles an e-science workflow (multiple intermediate inputs/outputs on the filesystem), so we added non-containerized Snakemake workflows from prior work [@graysonAutomaticReproductionWorkflows2023].
-->

- **Data science**:
  None of the benchmarks resembled a typical data science program, so we added the most popular Notebooks from Kaggle.com, a data science competition website.

- **Compilations**:
  Prior work uses compilation of Apache or of Linux.
  We added compilation of several other packages (any package in Spack) to our benchmark.
  Compiling packages is a good use-case for a provenance tracer, because a user might trial-and-error multiple compile commands and not remember the exact sequence of "correct" commands;
  the provenance tracker would be able to recall the commands which did not get overwritten, so the user can know what commands "actually worked". ^[DSK: this reminds me of VisTrails from Utah]

<!--
- **Computational simulations**:
  High-performance computing (HPC) scientific simulations could benefit from provenance tracing.
  These HPC applications may have access patterns quite different than conventional desktop applications.
  The xSDK framework [@bartlettXSDKFoundationsExtremescale2017] collects a ^[DSK: end is missing]
-->

## Performance Experiment

To get consistent measurements, we select as many benchmarks and provenance tracers as we reasonably can, and run a complete matrix (every tracer on every benchmark).
@Tbl:machine describes our experimental machine.
We use BenchExec [@beyerReliableBenchmarkingRequirements2019] to precisely measure the CPU time, wall time, memory utilization, and other attributes of the process (including child processes) in a Linux CGroup without networking, isolated from other processes on the system with ASLR.
ASLR does introduce non-determinism into the execution time, but it randomizes a variable that may otherwise have confounding effect [@mytkowiczProducingWrongData2009].

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
\bottomrule
\end{tabular}
\end{center}
%\end{minipage}
\end{table}

## Benchmark Subsetting

We implemented and ran many different benchmarks, which may be costly for future researchers seeking to evaluate new provenance collector.
A smaller, less-costly set of benchmarks may be sufficiently representative of the larger set.

Following Yi et al. [@yiEvaluatingBenchmarkSubsetting2006], we evaluate the benchmark subset in two different ways:

1. **Accuracy**.
   How closely do features of the subset resemble features of the original set?
   We will evaluate this by computing the root-mean squared error of a "non-negative" "linear regression" from the "standardized" features of selected benchmarks to the mean of features of the total set.

   - We use a "linear regression" to account for the possibility that the total set has unequal proportions of benchmark clusters.
     Suppose it contained 10 programs of type A, which all have similar performance, and 20 of type B: the benchmark subset need not contain two B programs and onerous A program.
     We would rather have one A, one B, and write the total performance as a weighted combination of the performance of $A$ and $B$, perhaps $1 \cdot \mathrm{perf}_A + 2 \cdot \mathrm{perf}_B$).
     We normalize these weights by adding an ancillary constant feature, so $\mathrm{weight}_A + \mathrm{weight}_B + \dotsb = 1$.
     Yi et al. [@yiEvaluatingBenchmarkSubsetting2006] were attempting to subset with SPEC CPU 2006, which one can assume would already be balanced in these terms, so their analysis uses an unweighted average.

   - We require the linear regression to be "non-negative" so that the benchmark subset is monotonic; doing better on every benchmark in the subset should result in doing better on the total set.

   - "Standardized" means we transform raw features $x$ into $z_x = (x - \bar{x}) / \sigma_x$.
     While $x$ is meaningful in absolute units, $z_x$ is meaningful in relative terms (i.e., a value of 1 means "1 standard deviation greater than the mean").
     Yi et al., by contrast, only normalize their features $x_{\mathrm{norm}} = x / x_{\max}$ which does not take into account the mean value.
     We want our features to be measured relative to the spread of those features in prior work.

2. **Representativeness.**
   How close are benchmarks in the original set to benchmarks in the subset?
   We will evaluate this by computing root mean squared error (RMSE) on the euclidean distance of standardized features from each benchmark in the original set to the closest benchmark in the selected subset.

   - We opt for RMSE over mean absolute error (MAE), used by Yi et al. [@yiEvaluatingBenchmarkSubsetting2006], because RMSE punishes outliers more.
     MAE would permits some distances to be large, so long it is made up for by other distances are small.
     RMSE would prefer a more equitable distribution, which might be worse on average, but better on the outliers.
     We think this aligns more with the intent of "representativeness."

For features, we will use features that are invariant between running a program ten times and running it once.
This gives long benchmarks and short benchmarks which exercise the same functionality similar feature vectors.
In particular, we use:

- The log overhead ratio of running the benchmark in each provenance collectors.
  We use the logarithm of the ratio, rather than the ratio directly because the logarithm is symmetric with respect to overshooting and undershooting.
  Suppose \$x provenance collector runs benchmark \$y1 twice as fast and benchmark \$y2 twice as slow; the average of the overhead would be $(2 + \frac{1}{2}) / 2 = 1.25$, whereas the average of the logarithms would be $\log 2 + \log \frac{1}{2} = \log 2 - \log 2 = 0$, meaning the 2x speedup "canceled out" the 2x slowdown on average). 
  Note that the arithmetic mean of logarithms of a value is equivalent to the geometric mean of the value.

- The ratio of CPU time to wall time.

- The number of syscalls in each category per wall time second, where the categories consist of socket-related syscalls, syscalls that read file metadata, syscalls that write file metadata, syscalls that access the directory structure, syscalls that access file contents, exec-related syscalls, clone-related syscalls, exit-related syscalls, dup-related syscalls, pipe-related syscalls, close syscalls, pipe-related syscalls, and chdir syscalls.

In order to choose the subset, we will try clustering, preceded by optional dimensionality reduction.
Once the benchmarks are grouped into clusters, we identify one benchmark from each of the $k$ clusters to consist the benchmark subset.
We will sweep across $k$.
We tried the following clustering algorithms:

- **K-means.** K-means [@macqueenMethodsClassificationAnalysis1965] greedily minimizes within-cluster variance, which is equivalent to the "representativeness" RMSE distance we want to minimize.
  Unfortunately, k-means can easily get stuck in local minima and needs to take the number of clusters, $k$, as a parameter.
  We use random restarts and initialize with k-means++ [@arthurKmeansAdvantagesCareful2007].

- **Agglomerative clustering (Ward linkage).**
  Agglomerative clustering [@wardjr.HierarchicalGroupingOptimize1963] greedily minimizes a certain metric from the bottom up.
  All data points start out as singleton clusters, and the algorithm joins the "best" two clusters repeatedly.
  The Ward Linkage is a metric that joins the pair of clusters resulting in the smallest within-cluster variance, which is exactly what "representativeness" RMSE distance wants to minimize.
  Agglomerative clustering can output hierarchical clusters, which may be useful in other contexts.

Dimensionality reduction seeks transform points in a high-dimensional space to points in a low-dimensional space, while preserving some property or properties (often including pairwise distance).
We experiment with no dimensionality reduction and with PCA dimensionality reduction, while sweeping on the number of target dimensions.

## Performance Model

A related problem to subsetting is inferring a performance model.
There are two motivations for inferring a performance model:

- A sysadmin may wish to provide a computational provenance capturing system to their institution, but getting approval to run new software on their system may be expensive (e.g., on highly secure systems, the sysadmin may need to acquire a security audit of the code before it can be approved for use).
  They may want to prospectively estimate the overhead of provenance collectors without having to install all the provenance collectors on their system, so they can select the optimal collector for their use-case.

- Inferring a provenance model may improve our understanding of the bottlenecks in provenance collectors.

A performance model should input features of a prospective workload and output the approximate overhead under different systems.
A priori, provenance collectors put a "tax" on certain syscalls (e.g., file I/O operations, process forks, process execs), because the system has to intercept and record these
Therefore, we expect a low-dimensional linear model (perhaps number of I/O operations per second times a weight plus number of forks per second times another weight) would predict overhead optimally.
To estimate this, we use the following models:

- **Ordinary least-squares (OLS) linear regression**.
  We estimate the runtime of each benchmark on each provenance collector as a linear regression of the features of each benchmark, learning weights for each feature in each provenance collector using ordinary least-squares.
  This would create a model like $\mathrm{weight}_1 \cdot \mathrm{feature}_1 + \mathrm{weight}_2 \cdot \mathrm{feature}_2 + \cdots$
  However, we can reduced its number of parameters, and thereby increase its out-of-domain generalizability, by the next two methods.

- **Low-rank linear regression.**
  To further reduce the number of parameters, we apply singular value decomposition (SVD) to create a lossily-compressed representation of the learned weights.
  TODO: describe this model

- **OLS on a subset of features.**
  This method proceeds like the OLS regression, except it only uses a subset of the features, ignoring the rest.
  This is like doing a LASSO regression, but with multiple linear predictors sharing the same set of features (LASSO is usually described as solving for just one linear predictor).
  Unfortunately, we do not know an efficient algorithm like ID for selecting this subset.
  We tried two algorithms: greedy, which picks one additional feature that decreases loss the most until it has $k$ features, and random, which selects a random $k$-sized subset.

We use the same features as in \Cref{benchmark-subsetting}, but with the addition of a constant term, for a provenance collectors which have a fixed startup cost.

We use cross-validation to estimate generalizability of the predictor.
Cross-validation proceeds in the following manner, given $n$ benchmarks and $f$ features.

1. Separate the $n$ benchmarks into $\alpha n$ "testing" benchmarks and $(1 - \alpha)n$ "training" benchmarks.

2. Learn to predict the log overhead ratio based on  $f$ features of each of the $(1-\alpha)n$ training benchmarks.

3. Using the model learned in the previous step, predict the log overhead ratio on $\alpha n$ testing benchmarks.

4. Compute the RMSE of the difference between predicted and actual.

5. Repeat to 1 with a different, but same-sized test/train split.

6. Take the arithmetic average of all observed RMSE; this is an estimate of the RMSE of the predictor on out-of-sample data.

While cross-validation does punish model-complexity and overfitting to some extent, we will still take the number of parameters into account when deciding the "best" model in the interest of epistemic modesty.
Preferring fewer parameters makes the model more generalizable on out-of-domain data, since even our full cross-validation data is necessarily incomplete.

# Results

## Selected Provenance Collectors

@Tbl:tools shows the provenance collectors we collected and their qualitative features.
The last column in the table categorizes the "state" of that provenance collector in this work into one of the following:

- **Not for Linux.**
  Our systems are Linux-based and Linux is used by many computational scientists.
  Therefore, we did not try to reproduce systems which were not Linux based.

- **VMs too slow.**
  Some provenance collectors require running the code in a virtual machine.
  We know a priori that these methods are prohibitively slow, with Panorama reporting 20x average overhead [@yinPanoramaCapturingSystemwide2007].
  The provenance systems we are interested in have overheads in the 1.01x -- 3x range.  [^DSK: maybe say instead that we don't use prov systems that have VM overheads over 3x?]

- **Requires recompilation.**
  Some provenance collectors require the user to recompile their entire application and library stack.
  This is prohibitively onerous and negates the otherwise low cost of switching to system-level provenance we are pursuing.

- **Requires special hardware.**
  Some methods require certain CPUs, e.g., Intel CPUs for a dynamic instrumention tool called Intel PIN.
  Being limited to certain CPUs violates our goal of promulgating reproducibility to as many people as possible.
  
- **No source.**
  We searched the original papers, GitHub, BitBucket, Google, and emailed the first author (CCing the others).
  If we still could not find the source code for a particular provenance collector, we cannot reproduce it.
  Note, however, that RecProv is implemented using rr, so we can use rr as a lower-bound for RecProv.
  
- **Requires custom kernel (Hi-Fi, LPM/ProvMon, CamFlow).**
  Collectors which modify Linux kernel code are out-of-scope for this work due to their increased maintenance overhead, security risk, and difficulty of system administration.
  Indeed, many of the systems are too old to be usable: LPM/ProvMon is a patch-set for Linux 2.6.32 (reached end-of-life 2016), Hi-Fi is a patch-set for Linux 3.2 (reached end-of-life in 2018).
  On the other hand, SingularityCE/Apptainer require Linux $\geq$ 3.8 for user namespaces.

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
  We tried to get this provenance system to run, with several weeks of effort: we emailed the original authors and other authors who used this system, and we left a GitHub issue describing the expected and actual results ^[See <https://github.com/dtg-FRESCO/opus/issues/1>].
  However, we still could not get the system to run properly.
  
- **Needs more time (DTrace, SPADE, eBPF/bpftrace).**
  We simply needed more time to implement these provenance collectors.

- **Partially reproduced (ltrace, CDE).**
  These are provenance collectors that we could reproduce on some workloads but not others.
  Missing values would complicate the data analysis too much, so we had to exclude these from our running-time experiment.

  - **ltrace**.
     ltrace is an off-the-shelf tool, available in most Linux package repositories, that uses `ptrace` to trace library calls matching a certain filter.
     Library calls are at a higher-level than syscalls.
     While we could run ltrace on some of our benchmarks, it crashed when processing on the more complex benchmarks.
     We localized the problem to the following code^[See <https://gitlab.com/cespedes/ltrace/-/blob/8eabf684ba6b11ae7a1a843aca3c0657c6329d73/handle_event.c#L775>]:

     \scriptsize

     ``` c
     /* FIXME: not good -- should use dynamic allocation. 19990703 mortene. */
     if (proc->callstack_depth == MAX_CALLDEPTH - 1) {
         fprintf(stderr, "%s: Error: call nesting too deep!\n", __func__);
         abort();
         return;
     }
     ```

     \normalsize

  - **CDE**.
    CDE is a research prototype proposed by Guo and Engler [@guoCDEUsingSystem2011].
    CDE is a record/replay tool.
    During record, CDE  uses `ptrace` to intercept its syscalls, and copy relevant files into an archive.
    During rerun, can use `ptrace` to intercept syscalls and redirect them to files in the archive.
    Sciunit uses a modified version of CDE that works on all of our benchmarks, so we can use that as a proxy.
    CDE can run some of our benchmarks, but crashes when trying to copy from the tracee process to the tracer due to `ret == NULL`[^cde-note]:

    \scriptsize

    ```c
    static char* strcpy_from_child(struct tcb* tcp, long addr) {
        char* ret = strcpy_from_child_or_null(tcp, addr);
        EXITIF(ret == NULL);
        return ret;
    }
    ```

    \normalsize

  [^cde-note]: See <https://github.com/usnistgov/corr-CDE/blob/v0.1/strace-4.6/cde.c#L2650>. The simplest explanation would be that the destination buffer is not large enough to store the data that `strcpy` wants to write. However, the destination buffer is `PATHMAX`.

- **Reproduced (Strace, FSAtrace, RR, ReproZip, Sciunit).**
  We reproduced this provenance collector on all of the benchmarks.

  - **strace**
    strace is a well-known system program that uses Linux's `ptrace` functionality to record syscalls, their arguments, and their return code to a file.
    strace even parses datastructures to write strings and arrays rather than pointers.
    TODO: strace configuration?

  - **fsatrace**
    Library-interpositioning is a technique where a program mimics the API of a standard library.
    Programs are written to call into the standard library, but the loader sends those calls to the interpositioning library instead.
    The interpositioning library can log the call and pass it to another library (possibly the "real" one), so the program's functionality is preserved.
    FSAtrace uses library-interpositioning to intercept file I/O calls.

  - **RR**
    RR [@ocallahanEngineeringRecordReplay2017] is a "record/replay" tool like CDE.
    TODO

  - **ReproZip**
    TODO

  - **PTU/Sciunit**
    TODO

\begin{table}
\caption{Provenance collectors from our search results and from experience.}
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
PTU/Sciunit \cite{phamUsingProvenanceRepeatability2013}            & tracing                      & Reproduced                 \\
CDE \cite{guoCDEUsingSystem2011}                                   & tracing                      & Partially reproduced       \\
ltrace                                                             & tracing                      & Partially Reproduced       \\
Namiki et al. \cite{namikiMethodConstructingResearch2023}          & audit                        &                            \\
PROV-IO \cite{hanPROVIOOCentricProvenance2022}                     & lib. ins.                    &                            \\
SPADE \cite{gehaniSPADESupportProvenance2012}                      & audit, FS, or compile-time   & Needs more time            \\
DTrace \cite{DTrace}                                               & audit                        & Needs more time            \\
LPS \cite{daiLightweightProvenanceService2017}                     & lib. ins.                    &                            \\
eBPF/bpftrace                                                      & audit                        & Needs more time            \\
SystemTap \cite{prasadLocatingSystemProblems2005}                  & audit                        & Needs more time            \\
OPUS \cite{balakrishnanOPUSLightweightSystem2013}                  & lib. ins.                    & Not reproducible           \\
CamFlow \cite{pasquierPracticalWholesystemProvenance2017}          & kernel ins.                  & Requires custom kernel     \\
Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}                   & kernel ins.                  & Requires custom kernel     \\
LPM/ProvMon \cite{batesTrustworthyWholeSystemProvenance2015}       & kernel ins.                  & Requires custom kernel     \\
RecProv \cite{jiRecProvProvenanceAwareUser2016}                    & tracing                      & No source                  \\
LPROV \cite{wangLprovPracticalLibraryaware2018}                    & kernel mod., lib. ins.       & No source                  \\
S2Logger \cite{suenS2LoggerEndtoEndData2013}                       & kernel mod.                  & No source                  \\
ProTracer \cite{maProTracerPracticalProvenance2016}                & kernel mod.                  & No source                  \\
FiPS \cite{sultanaFileProvenanceSystem2013}                        & FS                           & No source                  \\
PANDDE \cite{fadolalkarimPANDDEProvenancebasedANomaly2016}         & kernel ins., FS              & No source                  \\
PASS/Pasta \cite{muniswamy-reddyProvenanceAwareStorageSystems2006} & kernel ins., FS, lib. ins.   & No source                  \\
PASSv2/Lasagna \cite{muniswamy-reddyLayeringProvenanceSystems2009} & kernel ins.                  & No source                  \\
Lineage FS \cite{sarLineageFileSystem}                             & kernel ins.                  & No source                  \\
RTAG \cite{jiEnablingRefinableCrossHost2018}                       & dyn./static bin. ins.        & No source                  \\
BEEP \cite{leeHighAccuracyAttack2017}                              & dyn. bin. ins.               & Requires HW                \\
libdft \cite{kemerlisLibdftPracticalDynamic2012}                   & dyn. bin., kernel, lib. ins. & Requires HW                \\
RAIN \cite{jiRAINRefinableAttack2017}                              & dyn. bin. ins.               & Requires HW                \\
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

\begin{table}
\caption{Benchmarks used by prior works on provenance collectors (sorted by year of publication).}
\label{tbl:prior-benchmarks}
%\begin{minipage}{\columnwidth}
\begin{center}
\scriptsize
\begin{tabular}{p{0.21\linewidth}p{0.54\linewidth}p{0.12\linewidth}}
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
LPM/ProvMon \cite{batesTrustworthyWholeSystemProvenance2015} & lmbench, compile Linux, Postmark, BLAST                                                                                                         & Native                \\
Ma et al. \cite{maAccurateLowCost2015}                       & TextTransfer, Chromium, DrawTool, NetFTP, AdvancedFTP, Apache, IE, Paint, Notepad, Notepad++, simplehttp, Sublime Text                          & Native                \\
ProTracer \cite{maProTracerPracticalProvenance2016}          & Apache, miniHTTP, ProFTPD, Vim, Firefox, w3m, wget, mplayer, Pine, xpdf, MC, yafc                                                               & Auditd, BEEP          \\
LDX \cite{kwonLDXCausalityInference2016}                     & SPEC CPU 2006, Firefox, lynx, nginx, tnftp, sysstat, gif2png, mp3info, prozilla, yopsweb, ngircd, gocr, Apache, pbzip2, pigz, axel, x264        & Native                \\
PANDDE \cite{fadolalkarimPANDDEProvenancebasedANomaly2016}   & ls, cp, cd, lpr                                                                                                                                 & Native                \\
MPI \cite{maMPIMultiplePerspective2017}                      & Apache, bash, Evince, Firefox, Krusader, wget, most, MC, mplayer, MPV, nano, Pine, ProFTPd, SKOD, TinyHTTPd, Transmission, Vim, w3m, xpdf, Yafc & Audit, LPM-HiFi       \\
CamFlow \cite{pasquierPracticalWholesystemProvenance2017}    & lmbench, postmark, unpack kernel, compile Linux, Apache, Memcache, redis, php, pybench                                                          & Native                \\
BEEP \cite{leeHighAccuracyAttack2017}                        & Apache, Vim, Firefox, wget, Cherokee, w3m, ProFTPd, yafc, Transmission, Pine, bash, mc, sshd, sendmail                                          & Native                \\
RAIN \cite{jiRAINRefinableAttack2017}                        & SPEC CPU 2006, cp linux, wget, compile libc, Firefox, SPLASH-3                                                                                  & Native                \\
Sciunit \cite{tonthatSciunitReusableResearch2017}            & Workflows (VIC, FIE)                                                                                                                            & Native                \\
LPS \cite{daiLightweightProvenanceService2017}               & IOR benchmark, read/write, MDTest, HPCG                                                                                                         & Native                \\
LPROV \cite{wangLprovPracticalLibraryaware2018}              & Apache, simplehttp, proftpd, sshd, firefox, filezilla, lynx, links, w3m, wget, ssh, pine, vim, emacs, xpdf                                      & Native                \\
MCI \cite{kwonMCIModelingbasedCausality2018}                 & Firefox, Apache, Lighttpd, nginx, ProFTPd, CUPS, vim, elinks, alpine, zip, transmission, lftp, yafc, wget, ping, procps                         & BEEP                  \\
RTAG \cite{jiEnablingRefinableCrossHost2018}                 & SPEC CPU 2006, scp, wget, compile llvm, Apache                                                                                                  & RAIN                  \\
URSPRING \cite{rupprechtImprovingReproducibilityData2020}    & open/close, fork/exec/exit, pipe/dup/close, socket/connect, CleanML, Vanderbilt, Spark, ImageML                                                 & Native, SPADE         \\
PROV-IO \cite{hanPROVIOOCentricProvenance2022}               & Workflows (Top Reco, DASSA), H5bench                                                                                                            & Native                \\
Namiki et al. \cite{namikiMethodConstructingResearch2023}    & BT-IO                                                                                                                                           & Native                \\
\bottomrule
\normalsize
\end{tabular}
\end{center}
%\end{minipage}
\end{table}
\footnotetext{LogGC measures the offline running time and size of garbage collected logs; there is no comparison to native would be applicable.}

Of these, @Tbl:prior-benchmarks shows the benchmarks used to evaluate each tool, of which there are quite a few.
<!-- First, we eliminated several benchmarks from this set as non-starters for the reasons described in @Tbl:excluded-bmarks. -->
We prioritized implementing frequently-used benchmarks, easy-to-implement benchmarks, and benchmarks that we believe have value in representing a computational science use-case.

- **HTTP/FTP servers/clients/traffic.**
  The most common benchmark class from prior work, HTTP servers/traffic, HTTP servers/clients, FTP servers/traffic, and FTP servers/clients are popular because prior work focuses overwhelmingly on provenance for the sake of security (auditing, intrusion detection, or digital forensics).
  While these benchmarks may not be specifically relevant for computational science workloads, we wanted to include them in our suite to improve our coverage of benchmarks used frequently in prior works.
  We deprioritized implement additional FTP and HTTP clients and servers beyond the most common ones, because they would likely exhibit similar performance.

- **Compiling packages.**
  Compiling packages from source is a common operation in computational science, so we implemented as many of these as we could and also implemented some of our own.
  However, compiling LLVM takes more than twice as long as the longest benchmark, so we excluded LLVM specifically from the benchmark suite.
  We implemented a pattern for compiling packages from Spack that discounts the time taken to download sources, counting only the time taken to unpack, patch, configure, compile, link, and install them.
  We try compiling Python, Boost, HDF5, glibc, Apache HTTPd, and Perl.^[TODO: Double check what are we compiling? Also update the table below, once that is nailed down.]

- **Browsers.**
  Implementing headless for browsers in "batch-mode" without GUI interaction is not impossibly difficult, but non-trivial.
  Furthermore, we deprioritized this benchmark because few computational science applications resemble the workload of a web browser.

- **Un/archive.**
  Archive and unarchiving is a common task for retrieving data or source code.
  We benchmark un/archiving several archives with several compression algorithms.
  Choosing a compression algorithm may turn an otherwise I/O-bound workload to a CPU-bound workload, which would make the impact of provenance tracing smaller.

- **I/O microbenchmarks (lmbench, postmark, custom).**
  These could be informative for explicating which I/O operations are most affected.
  Prior work uses lmbench [@mcvoyLmbenchPortableTools1996], which focuses on syscalls generally, Postmark [@katcherPostMarkNewFile2005], which focuses on I/O operations, and custom benchmarks, for example running open/close in a tight loop.
  We use the specific lmbench cases from prior work, which is mostly the latency benchmarks with a few bandwidth benchmarks.
  Most provenance systems do not affect the bandwdith; it doesn't matter *how much* this process writes to that file, just *that* this process wrote to that file.

- **BLAST.**
  BLAST [@altschulBasicLocalAlignment1990] is a search for a fuzzy string in a protein database.
  Many prior works use this as a file-read heavy benchmark, as do we.
  This code in particular resembles a computational science workload.
  However, unlike prior work, we split the benchmark into each of each subtasks; provenance may have a greater overhead on certain subtasks.

- **CPU benchmarks.**
  SPEC CPU INT 2006 [@henningSPECCPU2006Benchmark2006] and SPLASH-3 [@sakalisSplash3ProperlySynchronized2016] test CPU performance.
  While we do not expect CPU benchmarks to be particularly enlightening for provenance collectors, which usually only affect I/O performance, it was used in three prior works, so we tried to implement both.
  However, SPEC CPU INT 2006 is not free (as in beer), so we could only implement SPLASH-3.

- **Sendmail.**
  Sendmail is a quite old mail server program.
  Mail servers do not resemble a computational science workload, and it is unclear what workload we would run against the server.
  Therfore, we deprioritized this benchmark and did not implement it.

- **VCS checkouts.**
  VCS checkouts are a common computational science operation.
  Prior work uses Mercurial, but we implemented Mercurial and Git.
  We simply clone a repository (untimed) and run `$vcs checkout` for random commits in the repository (timed).

- **Data processing/machine-learning Workflows.**
  VIC, FIE, ImageML, and Spark are real-world examples of scientific workflows.
  We would like to implement these, but reproducing those workflows is non-trivial; they each require their own computational stack.
  For FIE, in particular, there is no script that glues all of the operations together; we would have to read the publication [@billahUsingDataGrid2016] which FIE supports to understand the workflow, and write our own script which glues the operations together.

- **Utilities (bash, cp, ls, procps).**
  We did not see a huge representative value in these benchmarks that would not already be gleaned from lmbench, but due to its simplicity, we implemented it anyway.
  For `bash`, we do not know what workload prior works are using, but we test the speed of incrementing an integer and changing directories (`cd`).

- The rest of the programs are mostly specific desktop applications used only in one prior work.
  These would likely not yield any insights not already yielded by the benchmarks we implemented, and for each one we would need to build it from source, find a workload for it, and take the time to run it.
  They weigh little in the argument that our benchmark suite represents prior work, since they are only used in one prior work.

\begin{table}
\caption{Benchmarks implemented by this work. For brevity, we consider categories of benchmarks in @Tbl:prior-benchmarks. TODO: update this table with latest lit results.}
\label{tbl:implemented-benchmarks}
%\begin{minipage}{\columnwidth}
\begin{center}
\scriptsize
\begin{tabular}{p{0.05\linewidth}p{0.22\linewidth}p{0.6\linewidth}}
\toprule
Prior works & This work                 & Benchmark group and examples from prior work                                                                   \\
\midrule
10          & yes (5/7 servers)         & HTTP server/traffic ({Apache httpd, miniHTTP, simplehttp, lighttpd, Nginx, tinyhttpd, cherokee} x apachebench) \\
9           & yes (2/4 clients)         & HTTP serer/client (simplehttp x \{curl, wget, prozilla, axel\})                                                \\
8           & yes (3/5 orig + 4 others) & Compile user packages (Apache, LLVM, glibc, Linux, LaTeX document)                                             \\
8           & no                        & Browsers (\{Firefox, Chromium\} x Sunspider)                                                                   \\
6           & yes (1/6) + 2 others      & FTP client (lftp, yafc, tnftp, skod, AdvancedFTP, NetFTP)                                                      \\
5           & yes                       & FTP server/traffic (ProFTPd x ftpbench)                                                                        \\
5           & yes                       & Un/archive (\{compress, decompress\} x \{nothing, bzip2, pbzip, gzip, pigz\})                                  \\
5           & yes                       & I/O microbenchmarks (Postmark, lmbench, custom)                                                                \\
4           & yes                       & BLAST                                                                                                          \\
3           & yes (1/2)                 & CPU benchmarks (SPEC CPU INT 2006, SPLASH-3)                                                                   \\
3           & yes                       & Coreutils and other utils (bash, cp, ls, procps)                                                               \\
2           & no                        & Sendmail                                                                                                       \\
1           & yes                       & VCS checkouts (Mercurial)                                                                                      \\
1           & no                        & Machine learning workflows (CleanML, Spark)                                                                    \\
1           & no                        & Data processing workflows (VIC, FIE)                                                                           \\
1           & no                        & RUBiS                                                                                                          \\
1           & no                        & x264                                                                                                           \\
1           & no                        & mysqld                                                                                                         \\
1           & no                        & gocr                                                                                                           \\
1           & no                        & Memcache                                                                                                       \\
1           & no                        & Redis                                                                                                          \\
1           & no                        & php                                                                                                            \\
1           & no                        & pybench                                                                                                        \\
1           & no                        & ImageML                                                                                                        \\
1           & no                        & ping                                                                                                           \\
1           & no                        & mp3info                                                                                                        \\
1           & no                        & ngircd                                                                                                         \\
1           & no                        & CUPS                                                                                                           \\
\bottomrule
\end{tabular}
\end{center}
\end{table}

<!-- | 7 | Text-based browsers (w3m, lynx, elinks)                                                                              | Interactive                                           | -->
<!-- | 7 | TUI apps (Vim, nano, sysstat, mc, emacs, alpine, pine)                                                               | Interactive                                           | -->
<!-- | 5 | GUI apps (xpdf, Audacious, Sublime Text, Notepad++, Evince, Krusader, Mplayer, mpv, Transmission, FileZilla, Pidgin) | Interactive                                           | -->
<!-- | 1 | Windows programs (Notepad, Paint, IE)                                                                                | Wrong platform                                        | -->
<!-- | 1 | gif2png                                                                                                              | Unknown program (dozens of programs called "gif2png") | -->
<!-- | 1 | Vanderbilt                                                                                                           | Unknown program                                       | -->
<!-- | 1 | TextTransfer                                                                                                         | Unknown program                                       | -->
<!-- | 1 | DrawTool                                                                                                             | Unknown program                                       | -->
<!-- | 1 | yopsweb                                                                                                              | Unknown program                                       | -->

<!-- : Benchmarks rejected by this work {#tbl:rejected-bmarks} -->

\begin{table}
\caption{
This table shows percent overhead of the mean walltime when running with a provenance collector versus running without provenance.
A value of 1 means the new execution takes 1\% longer than the old.
"Noprov" refers to a system without any provenance collection (native), for which the slowdown is 0 by definition.
fsatrace appears to have a negative slowdown in some cases  due to random statistical noise.
}
\label{tbl:benchmark-results}
%\begin{minipage}{\columnwidth}
\begin{center}
\small
\begin{tabular}{llllll}
\toprule
collector & fsatrace & noprov & reprozip & rr & strace \\
benchmark types &  &  &  &  &  \\
\midrule
archive & 7 & 0 & 164 & 208 & 180 \\
blast & -1 & 0 & 32 & 102 & 6 \\
copy & 48 & 0 & 7299 & 322 & 710 \\
ftp client & -0 & 0 & 14 & 5 & 4 \\
ftp server & 1 & 0 & 58 & -32 & 65 \\
gcc & 3 & 0 & 417 & 314 & 321 \\
http client & -16 & 0 & 453 & 200 & 98 \\
http server & 6 & 0 & 791 & 965 & 516 \\
lmbench & -14 & 0 & 31 & 15 & 5 \\
notebook & -10 & 0 & 116 & 0 & 50 \\
pdflatex & -10 & 0 & 290 & 19 & 79 \\
postmark & 9 & 0 & 2002 & 367 & 928 \\
python & 0 & 0 & 412 & 137 & 184 \\
shell & 18 & 0 & 4620 & 698 & 63 \\
simple & 23 & 0 & 977 & 1749 & 431 \\
splash-3 & -1 & 0 & 78 & 64 & 19 \\
unarchive & 6 & 0 & 179 & 190 & 177 \\
vcs & 3 & 0 & 453 & 169 & 185 \\
\bottomrule
\end{tabular}
\end{center}
%\end{minipage}
\end{table}
<!--
TODO: put geomean overhead per prov collector
TODO: put measure of uncertainty.
TODO: Wang et al. report ltrace
-->

Although SPLASH-3 CPU-oriented benchmarks contain mostly CPU-bound tasks, they often need to load data from a file, which does invoke the I/O subsystem.
They are CPU benchmarks when the CPU is changed and the I/O subsystem remains constant, but when the CPU is constant and the I/O subsystem is changed, the total running time is influenced by I/O-related overhead.

## Subsetted Benchmarks

\begin{figure*}
\subcaptionbox{
  Subsetting algorithms scored by the RMSE of the distance of each benchmark to the nearest selected benchmark.
  A dotted line shows the x- amd y-value of the point of diminishing return.
}{
  \includegraphics[width=0.44\textwidth]{generated/subsetting-dist.pdf}
  \label{fig:subsetting-dist}
}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Subsetting algorithms scored by the RMSE of the difference between (weighted) features of the subset and features of the original set.
  A dotted line shows the x- amd y-value of the point of diminishing return.
}{
  \includegraphics[width=0.48\textwidth]{generated/subsetting-accuracy.pdf}
  \label{fig:subsetting-accuracy}
}
\caption{Competition for best benchmark subsetting algorithm, sweeping over subset size on the x-axis.}
\label{fig:subsetting}
\end{figure*}

@Fig:subsetting shows the performance of various algorithms on benchmark susbetting.
We observe:

- The features are already standardized, so PCA has little to offer other than rotation and truncation.
  However, the truncation is throwing away potentially useful data.
  Since we have a large number of benchmarks, and the space of benchmarks is quite open-ended, the additional dimensions that PCA trims off appear be important for separating clusters of data.

- K-means and agglomerative clustering yield nearly the same results.
  They both attempt to minimize within-cluster variance, although by different methods.

- RMSE of the residual of linear regression will eventually hit zero because the $k$ exceeds the rank of the matrix of features by benchmarks;
  The linear regression has enough degrees of freedom to perfectly map the inputs to their respective outputs.

It seems that agglomerative clustering with $k=20$ has quite good performance, and further increases in $k$ exhibit diminishing returns.
We examine the generated clusters and benchmark subset in @Fig:subset and @Fig:dendrogram.

\begin{figure*}
\subcaptionbox{
  Benchmark subset, where color shows a posteriori agglomerative clusters.
  The same-color small dots are benchmarks in the same cluster, the "x" of that color is their hypothetical benchmark with their average features, and the big dot of that color is the closest actual benchmark to the average of their features.
  A benchmark subset replaces each cluster of small dots with just the single big dot.
}{
  \includegraphics[width=0.45\textwidth]{generated/pca0.pdf}
  \label{fig:benchmark-clusters}
}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Benchmark subset, where color shows a priori benchmark ``type'' (see \Cref{tbl:implemented-benchmarks}).
  For example, archive-with-gzip and archive-with-bzip2 are two benchmarks of the same type, and therefore color.
  The "x" still shows a posteriori cluster centers as in \Cref{fig:benchmark-clusters}.
}{
  \includegraphics[width=0.45\textwidth]{generated/pca1.pdf}
  \label{fig:benchmark-groups}
}
\caption{Benchmarks, clustered agglomeratively into 20 subsets using standardized performance features. These axes show only two dimensions of a high-dimensional space. We apply PCA *after* computing the clusters, in order to project the data into a 2D plane.}
\label{fig:benchmark-pca}
\end{figure*}


<!-- TODO: Explain multiple iterations and averageing -->

@Fig:benchmark-clusters 
shows the a posteriori clusters with colors.
@Fig:benchmark-groups shows a priori benchmark "types", similar but more precise than those in @Tbl:implemented-benchmarks.
From these two, we offer the following observations:

- It may appear that the algorithm did not select the benchmark closest to the cluster center, but this is because we are viewing a 2D projection of a high-dimensional space, like how three stars may appear next to each other in the sky, but in reality one pair may be much closer than the other, since we cannot perceive radial distance to each star.
n
- Many of the clusters are singletons, for example the `python http.server` near $(5,6)$; this is surprising, but given there are not any other points nearby, it seems reasonable.

- We might expect that benchmarks of the same type would occupy nearby points in PCA space, but it seems they often do not.
  lmbench is particularly scattered with points at $(-1, 0)$ and $(0, 5)$, perhaps because it is a microbenchmark suite where each microbenchmark program tests a different subsystem.

\begin{figure*}
\begin{center}
\subcaptionbox{
  Dendrogram showing the distance between clusters.
  We label each cluster by their "selected benchmark".
  If there is a colon and a number after the name, it indicates the number of benchmarks contained in that cluster.
  Otherwise, the cluster is a singleton.
}{
  \includegraphics[width=0.56\textwidth]{generated/dendrogram.pdf}
  \label{fig:dendrogram}
}
\hspace{0.03\textwidth}
\subcaptionbox{
  A table showing cluster membership and weights.
  The weights show one way of approximating the features in the original set, which is by multiplying the features of the cluster representative by the weight and summing over all clusters.
}{
\scriptsize
  \begin{tabular}{p{0.07\textwidth}p{0.04\textwidth}p{0.18\textwidth}}
  \toprule
  Cluster representative & Weight (\%) & Cluster members \\
  \midrule
unarchive pigz                 &  26.4 & git setuptools\_scm, python-hello-world, unarchive, unarchive gzip, wget \\
lm-protection-fault            &  24.2 & a-data-sci, blastp, blastx, lm-bw\_file\_rd, lm-bw\_pipe, lm-bw\_unix, lm-catch-signal, lm-getppid, lm-install-signal, lm-mmap, lm-page-fault, lm-read, lm-select-file, lm-select-tcp, lm-write, megabl, splash-cholesky, splash-lu, splash-ocean, splash-radiosity, splash-radix, splash-volrend, splash-water-nsquared, splash-water-spatial, tblast \\
latex-test                     &  13.0 & archive bzip2, archive gzip, blastn, comprehens, curl, latex-test2, lm-fstat, lm-stat, minihttp, python-import, titanic-da, unarchive bzip2 \\
unarchive pbzip2               &  7.9 & archive pbzip2, archive pigz, lighttpd \\
lm-fs                          &  3.9 & lm-open/close \\
lm-exec                        &  3.7 &  \\
shell-incr                     &  3.1 & splash-fft \\
proftpd with ftpbench          &  2.5 &  \\
ftp-curl                       &  2.4 & ftp-wget, lftp \\
cp linux                       &  2.0 &  \\
ls                             &  1.7 & echo, hello, ps, true \\
shell-echo                     &  1.5 &  \\
nginx                          &  1.5 &  \\
apache                         &  1.4 &  \\
cd                             &  1.4 &  \\
python http.server             &  1.3 &  \\
gcc-hello-world threads        &  0.7 & gcc-hello-world \\
lm-fork                        &  0.1 &  \\
postmark                       &  0.0 & archive, cp smaller \\
hg schema-validation           &  0.0 &  \\
\midrule
all\footnote{Since these are coefficients, not proportions, the result need not add to 100\%, although we include an equation which rewards the solver when it gets the sum close to 100\%.}
                               & 98.8 & \\
  \bottomrule
  \normalsize
  \end{tabular}
  \label{tbl:members}
}
\caption{Figures showing the relationships between clusters and the members of each cluster.}
\label{fig:subset}
\end{center}
\end{figure*}

To elucidate the structure of the clusters, we plotted a dendrogram (@Fig:dendrogram) and listed the members of each cluster (@Tbl:members).
We offer the following observations:

- Fork and exec are close in feature-space, probably because programs usually do both.

- cd and shell-echo are near each other.
  I is surprising that blastn is also near cd and shell-echo, but they both have similar cputime-to-walltime ratios.

- Many of the CPU-heavy workloads are grouped together, under lm-protection-fault.

- Many of the un/archive benchmarks are grouped together with lighttpd, which also accesses many files.

TODO: consider X-means, G-means, or something else to determine $k$.

## Predictive Model

@Fig:predictive-performance shows us the competition between predictive performance models.
Note that linear regression does not permit sweeping over the number of parameters; it requires a $n_{\mathrm{benchmarks}} n_{\mathrm{features}}$ parameters.
Matrix factorization methods use only $(n_{\mathrm{benchmarks}} - k) \times (n_{\mathrm{features}} - k) = n_{\mathrm{benchmarks}} n_{\mathrm{features}} - k(n_{\mathrm{benchmarks}} + n_{\mathrm{features}}) + k^2$ parameters.
When $k$ is low, matrix factorization is much fewer parameters than linear regression at the cost of some in-sample accuracy, but when $k$ approaches $n_{\mathrm{features}}$, it is less parameter-efficient than linear regression.
Number of parameters is not truly an independent variable that can be directly swept over.
Rather $k$ is an independent variable, we sweep over $k$, and plot the number-of-parameters on the x-axis, since that is more directly interpretable.
Models with a large number of parameters are more likely to overfit to spurious correlations on the test sample which generalize poorly on the train sample.
Overgeneralization is appropriately punished by cross-validation.

\begin{figure}
\begin{center}
\includegraphics[width=0.49\textwidth]{generated/predictive-performance.pdf}
\caption{Competition between predictive performance models.}
\label{fig:predictive-performance}
\end{center}
\end{figure}

We observe the following:

- When the number of parameters is large, all of the algorithms preform similarly;
  Even though greedy feature selection is more constrained than low-rank matrix factorization (every solution found by greedy is a candidate used by low-rank, but not vice versa), there are enough degrees of freedom to find similar enough candidates.

- Linear regression has equivalent goodness-of-fit to matrix factorization with a high $k$, as expected.
  When the compression factor is low, the compressed version is just as good as the original.

- Random-best usually does not do better than greedy feature selection.
  However, greedy is much easier to compute, evaluating $n_{\mathrm{features}}$ subsets of size 1, $n_{\mathrm{features}}-1$ subsets of 2, $\dotsc$ $n_{\mathrm{features}} - k + 1$ subsets of size $k$; random has to evaluate a large number (1000 in our case) of subsets of size $k$.
  Greedy is not necessarily optimal, since a set of features may be individually outscored by other features but may have predictive value when taken as a set. 
  Greedy would never pick that set, because it is bound to pick the best additional individual feature at every step, but random-best could.
  However, our problem domain may lack the complexity to generate these cases.

Greedy feature selection with 20 parameters (predicting the performance on 5 systems using only $k = 4$ of 16 features) seems to preform the best in cross-validation.
On 19 out of 20 cross-validation splits, greedy feature selection with $k=4$ chose the parameters in @Tbl:params.

\begin{table}
%\begin{minipage}{\columnwidth}
\begin{center}
\scriptsize
\begin{tabular}{p{0.04\textwidth}p{0.09\textwidth}p{0.09\textwidth}p{0.09\textwidth}p{0.09\textwidth}}
\toprule
 & metadata-reads per walltime second & constant fraction & cputime / walltime & execs-and-forks per walltime second \\
\midrule
fsatrace & 0.000003 & -0.001236 & -0.024958 & 0.000064 \\
nnnoprov & 0.000000 & 0.000000 & 0.000000 & 0.000000 \\
reprozip & 0.000043 & -0.027311 & 0.266969 & 0.000438 \\
rr & 0.000021 & -0.011208 & 0.404307 & 0.000878 \\
strace & 0.000029 & -0.002243 & 0.229129 & 0.000312 \\
\bottomrule
\end{tabular}
\caption{Linear regression, using benchmark subset to approximate the original benchmark.}
\label{tbl:params}
\end{center}
%\end{minipage}
\end{table}
\footnotesize

For example to estimate the overhead of fsatrace, we would use the first row of @Tbl:params,

$$
\begin{array}{rl}
\log \frac{\mathrm{walltime}_{\mathrm{fsatrace}}}{\mathrm{walltime}_{\mathrm{noprov}}} =
& 3 \times 10^{-6} \qty(\frac{\mathrm{metadata\ reads}}{\mathrm{walltime}_{\mathrm{noprov}}})
- 0.001 \cdot \qty(\frac{1}{\mathrm{walltime}_{\mathrm{noprov}}}) \\
& - 0.02 \cdot \qty( \frac{\mathrm{cputime}_\mathrm{noprov}}{\mathrm{walltime}_{\mathrm{noprov}}})
+ 6 \times 10^{-5} \cdot \qty(\frac{\mathrm{execs\ and\ forks}}{\mathrm{walltime}_{\mathrm{noprov}}}) \\
\end{array}
$$
\normalsize

<!-- TODO: consider a non-negative linear regression -->

The system calls features can be observed using strace.
The CPU time and wall time of noprov can be observed using GNU time.
One need not complete an entire execution to observe the these fatures; one merely needs to record the features until they stabilize (perhaps after several iterations of the main loop).

## Discussion

**Prior work focuses on security, not computational science.**
@Tbl:implemented-benchmarks shows the top-used benchmarks are server programs, followed by I/O benchmarks.
Server programs access a lot of small files, with concurrency, which is a different file-access pattern than scientific applications.
BLAST (used by 4 / 22 publications) is the only scientific program to be used as a benchmark by more than one publication.
Benchmark subsetting includes two^[TODO: Check when we have the final data] different BLAST programs, because they are sufficiently different than the rest.

**Security values infalibility with respect to adversaries**
One difference between security and computational science is that security-oriented provenance collectors have to work with adverserial programs:
there should be no way for the program to circumvent the provenance tracing, e.g. `PTRACE_DETACH`.
Computational science, on the other hand, may satisfied by a solution that *can* be intentionally circumvented by an uncooperative program, but would work most of the time, provided it can at least detect when provenance collection is potentially incomplete.
Interposing standard libraries, although circumventable, has been used by other tools [@xuDXTDarshanEXtended2017].

**Prior work on provenance collectors doesn't test on many workflows.**
Workflows, for the purposes of this discussion, are programs that are structured as a set of loosely coupled components whose execution order is determined by dataflow.
Workflows are important for computational science, but also other domains, e.g., online analytical processing (also known as OLAP).
Under this definition, non-trivial source-code compilation is a workflow.

**There is no standard benchmark set; prior work tests on sometimes-overlapping sets of benchmarks.**


**Provenance collectors vary in power, but fast-and-powerful could be possible.**
While all bear the title, provenance collector, some are **monitoring**, merely recording a history of operations, while others are **interrupting**, interrupt the process when the program makes an operation.
Fsatrace, Strace, and Ltrace are monitoring, while ReproZip, Sciunit, RR, and CDE are interrupting, using their interruption store a copy of the files that would be read or appended to by the process.
We expect the monitoring collectors to be faster than the interrupting collectors, but the performance of strace is not that far off of the performance of RR^[TODO: Find a better example when we have the latest data.].
Strace and rr both use ptrace, but strace does very little work while rr maintains may need to intercept and reinterpret the syscall, (see treatment of `mmap` in RR's publication [@ocallahanEngineeringRecordReplay2017]).
This suggests most of the overhead actually be due to `ptrace` and its incurred context switches.
None of the interrupting provenance collectors use library interposition or eBPF.
Perhaps a faster underlying method would allow powerful features of interrupting collectors  in a reasonable overhead budget.

## Threats to Validity

# Future Work

In the future, we plan to implement compilation for more packages, in particular xSDK [@bartlettXSDKFoundationsExtremescale2017] packages.

We encourage future work to consider implementing an interrupting provenance collector using library interposition or eBPF.

While none of the monitoring collectors we know of exploit it, monitoring can be run off the critical path;
the program need not wait for an I/O operation to be logged before continuing.

None of the interrupting collectors we know of exploit it, some of the interruption work may be "postponed";
if a file is read, it can be copied at any time unless/until it gets mutated.

# Conclusion

We hope this work serves as a part of a bridge from research to practical use of provenance collectors.
As such, we address practical concerns of a user wanting to use a provenance collector.
We identify the reproducible and usable provenance collectors from prior work, and we evaluate their performance on synthetic and real-world workloads.

\appendix

# Open source contributions

The actual benchmark set and statistical analysis are open-source:

- <https://github.com/charmoniumQ/prov-tracer/>

This work necessitated modifying Spack, Sciunit, PTU, jupyter-contrib-nbextensions, Nixpkgs, ftpbench, and benchexec.
Where appropriate, we submitted as pull-requests to the respective upstream projects.

The following are merged PRs developed as a result of this work:

- <https://github.com/depaul-dice/sciunit/pull/35>
- <https://github.com/depaul-dice/provenance-to-use/pull/4>
- <https://github.com/depaul-dice/provenance-to-use/pull/5>
- <https://github.com/spack/spack/pull/42159>
- <https://github.com/spack/spack/pull/42199>
- <https://github.com/spack/spack/pull/42114>
- <https://github.com/selectel/ftpbench/pull/5>
- <https://github.com/selectel/ftpbench/pull/4>
- <https://github.com/sosy-lab/benchexec/pull/984>
- <https://github.com/sosy-lab/benchexec/pull/990>
- <https://github.com/NixOS/nixpkgs/pull/263829>
- <https://github.com/NixOS/nixpkgs/pull/257396>

The following are open PRs developed as a result of this work:

- <https://github.com/spack/spack/pull/39902>
- <https://github.com/spack/spack/pull/42131>
- <https://github.com/spack/spack/pull/41048>
- <https://github.com/depaul-dice/sciunit/pull/36>
- <https://github.com/ipython-contrib/jupyter_contrib_nbextensions/pull/1649>
- <https://github.com/NixOS/nixpkgs/issues/268542>

# References
