---
from: markdown
verbosity: INFO
citeproc: yes
ccite-method: citeproc
bibliography: zotero
link-citations: yes
link-bibliography: yes
notes-after-punctuation: yes
title: A benchmark suite and performance analysis of user-space provenance systems
author:
  - name: Samuel Grayson
    orcid: 0000-0001-5411-356X
    email: grayson5@illinois.edu
    affiliation:
      institution: University of Illinois Urbana Champaign
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
      institution: University of Illinois Urbana Champaign
      department:
        - Department of Computer Science
        - National Center for Supercomputing Applications
        - Deparment of Electrical and Computer Engineering
        - School of Information Sciences
      streetaddress:  201 North Goodwin Avenue MC 258
      city: Urbana
      state: IL
      country: USA
      postcode: 61801-2302
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
      streetaddress: 1515 Eubank Blvd SE1515 Eubank Blvd SE
  - name: Darko Marinov
    orcid: 0000-0001-5023-3492
    email: marinov@illinois.edu
    affiliation:
      institution: University of Illinois Urbana Champaign
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

# Background

Computational provenance, "the computational input artifacts and computational processes that influenced a certain computational output artifact" [@freireProvenanceComputationalTasks2008], has many potential applications, including the following from Pimentel et al. [@pimentelSurveyCollectingManaging2019] and Sar and Cao [@sarLineageFileSystem]:

1. **Reproducibility**.
   A description of the inputs and processes used to generate a specific output can aid manual and automatic reproduction of that output[^acm-defns].
   Lack of reproducibility in computational experiments undermines the long-term credibility of science and hinders the day-to-day work of researchers.
   Empirical studies [@trisovicLargescaleStudyResearch2022; @graysonAutomaticReproductionWorkflows2023; @collbergRepeatabilityComputerSystems2016; @zhaoWhyWorkflowsBreak2012] show that reproducibility is rarely achieved in practice, probably due to its difficulty under the short time budget that scientists have available to spend on reproducibility.
   If reproducibility was easier to attain, perhaps because of automatic provenance tracking, it may improve the reproducibility rate of computational research.

   - **Manual reproducibility**.
     A user can Provenance data improves manual reproducibility, because users have a record of the inputs, outputs, and processes used to create a computational artifact.

   - **Automatic reproducibility**.
     Provenance data also has the potential to enable automatic reproducibility, if the process trace is detailed enough to be "re-executed".
     This idea is also called "software record/replay".
     However, not all provenance systems make this their goal.

   [^acm-defns]: "Reproduction", in the ACM sense, where a **different team** uses the **same artifacts** to generate the output artifact [@acminc.staffArtifactReviewBadging2020].

2. **Caching subsequent re-executions**.
   Computational science inquiries involves changing some code and re-executing the workflows (e.g., testing different clustering algorithms).
   In these cases, the user has to keep track of what parts of the code they changed, and which process have to be re-executed.
   However, an automated system could read the computational provenance graphs produced by previous executions, look at what parts of the code changed, and safely decide what processes need to be re-executed.
   The dependency graph would be automatically deduced, leaving less chance for a dependency-misspecification, unlike Make or CMake, which requires the user to manually specify a dependency graph.

3. **Comprehension**. 
   Provenance helps the user understand and document workflows.
   An automated tool that consumes provenance can answer queries like "What version of the data did I use for this figure?" and "Does this workflow include FERPA-protected data?".

4. **Data cataloging**.
   Provenance data can help catalog, label, and recall experimental results based on the input parameters.
   For example, a user might have run dozens of different versions of their workflow, and they may want to ask an automated system, "show me the results I previously computed based on that data with this algorithm?".

5. **Space compression**.
   If the provenance of a particular artifact is known, the artifact may be able to be deleted to save space, and regenerated by need.

One can capture computational provenance by modifying an application to report provenance data, leveraging a workflow engine or programming language to report provenance data, or leveraging an operating system to emit provenance data to report provenance data [@freireProvenanceComputationalTasks2008].

- **Application-level** provenance is the most semantically rich, since it knows the use of each input at the application-level (see @fig:app-lvl-prov), but the least general, since each application would have to be modified individually.

- **Workflow-level** or **language-level** provenance is a middle ground in semantic richness and generality;
  it only knows the use of inputs in a dataflow sense (see @fig:wf-lvl-prov), but all applications using the provenance-modified workflow engine or programming language would emit provenance data without themselves being modified to emit provenance data.

- **System-level** is the most general, since all applications on the system would emit provenance data, but it is the least semantically rich, since observed dependencies may overapproximate the true dependencies (see @fig:sys-lvl-log and @fig:sys-lvl-prov).
  System-level provenance collectors may be implemented in **kernel-space** or in **user-space**.
  Since kernel-space provenance collectors modify internals of the Linux kernel, it is a significant maintenance burden to keep them up-to-date as the kernel changes.
  High-security national labs may be wary of including a patched kernel.
  On the other hand, user-space collectors compromise performance in exchange for requiring less maintenance and less privilege.

<div id="fig:prov">

   \scriptsize

  ![Application-level prov](app-lvl-prov.svg){#fig:app-lvl-prov width=12%}
  ![Workflow-level prov](wf-lvl-prov.svg){#fig:wf-lvl-prov width=12%}
  ![System-level log](sys-lvl-log.svg){#fig:sys-lvl-log width=12%}
  ![System-level prov](sys-lvl-prov.svg){#fig:sys-lvl-prov width=12%}

  \normalsize

Several provenance graphs collected at different levels.

</div>

One may imagine an abstract tradeoff curve (@fig:cost-vs-enabling) between "enabling provenance applications such as reproducibility" as the horizontal axis increasing rightwards and "cost of implementation" that provenance data on the vertical axis increasing upwards).
A typical status quo, not collecting any provenance data and not using workflows, is at the bottom left:
  no added cost and does nothing to enable provenance applications.
System-level, workflow/language-level, and application-level are on a curve, increasing cost and enabling more provenance applications.

The initial jump in cost from nothing to system-level is low because the user need not change _anything_ about their application;
  they merely need to install some provenance tracer onto their system and run their code, without modifying it, in the tracer. ^[DSK: what about the performance penalty? Since you talk about performance in contributions, I think you have to introduce it here. SAG: This is referring to the "cost of switching from no-prov to prov", which is low, and I'm only using this argument to explain why I look at system-level over the others. Performance overhead between system-level tools is a concern that I will address later on.]
Perceived ease of use is a critical factor in the adoption of new technologies (formalized in the Technology Acceptance Model [@davisTechnologyAcceptanceModel1985]).
Although the user may eventually use more semantically rich provenance, low-cost system-level provenance would get provenance's "foot in the door". 
While this data is less rich than that of the workflow or application level, it may be enough to enable important applications such as reproducibility, caching, etc.
Since system-level provenance collection is a possibly valuable tradeoff between cost and enabling provenance applications, system-level provenance will be the subject of this work.

While there is little cost human-overhead in using system-level provenance (no user code change), there is a non-trivial implicit overhead in monitoring and recording each computational process.
Even a minor overhead per I/O operation would get amplified over the tens of thousands of I/O operations that a program might execute per second.

Prior work in system-level provenance usually contains some benchmark programs to evaluate the overhead imposed by the system-level provenance tool.
However, the set of chosen benchmark programs are not consistent from one publication to another, and overhead can be extermely sensitive to the exact choice of program, so results are totally incomparable between publications.
Most publications only benchmark their new system against native/no-provenance, so prior work cannot easily establish which system-level provenance tool is the fastest.

# Contributions

This work aims to summarize state of the art, establish goalposts for future research in the area, and identify which provenance tools are practically usable.

This work contributes:

- **A rapid review**:
    There are scores of academic publications on system-level provenance (see @tbl:tools), so we collate as many provenance tools as possible and classify them by _capture method_ (e.g., does the provenance collector require you to load a kernel module or run your code in a VM?). 

- **A benchmark suite**:
  Prior work does not use a consistent set of benchmarks; often publications use an overlapping set of benchmarks from prior work.
  We collate benchmarks used in prior work, add some unrepresented areas, and find a statistically valid subset of the benchmark.

- **A quantitative performance comparison**:
  Prior publications often only compares the performance their provenance tool to the baseline, no-provenance performance, not to other provenance tools.
  It is difficult to compare provenance tools, given data of different benchmarks on different machines.
  This work runs a consistent set of benchmarks on a single machine over all provenance tools.

- **A predictive performance model**:
  The performance overhead of a single provenance system varies from <1% to 23% [@muniswamy-reddyLayeringProvenanceSystems2009] based on the application, so a single number for overhead is not sufficient.
  This work develops a statistical model for predicting the overhead of \$X application in \$Y provenance system based on \$Y provenance system's performance on our benchmark suite and \$X application's performance characteristics (e.g., number of I/O syscalls).

# Methods

## Rapid review

We began a rapid review to identify the research state-of-the-art tools for automatic system-level provenance.

Rapid Reviews are a lighter-weight alternative to systematic literature reviews with a focus on timely feedback for decision-making.
Schünemann and Moja [@schunemannReviewsRapidRapid2015] show that Rapid Reviews can yield substantially similar results to a systematic literature review, albeit with less detail.
Although developed in medicine, Cartaxo et al. show that Rapid Reviews are useful for informing software engineering design decisions [@cartaxoRoleRapidReviews2018; @cartaxoRapidReviewsSoftware2020].

We conducted a rapid review with the following parameters:

- **Objective**: Identify system-level provenance collection tools.

- **Search terms**: "system-level" AND "provenance"

- **Search engine**: Google Scholar

- **Number of results**: 50

  - This threshold is the point of diminishing returns, as no new tools came up in the 40th – 50th results.

- **Criteria**: A relevant publication would center on one or more operating system-level tools that capture file provenance. A tool requiring that the user use a specific application or platform would be irrelevant.

We record the following features for each system-level provenance tool:

- **Capture method**: What method does the tool use to capture provenance?

  - **User-level tracing**:
    A provenance tool may use "debugging" or "tracing" features provided by the kernel to trace the I/O operations of another program, e.g., `ptrace(2)` [@Ptrace].

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

## Benchmark selection

Using the tools selected above, we identified all benchmarks that have been used in prior work.
We excluded benchmarks for which we could not even find the original program (e.g., TextTransfer), benchmarks that were not available for Linux (e.g., Internet Explorer), benchmarks with a graphical component (e.g., Notepad++) , or benchmarks with an interactive component (e.g., GNU Midnight Commander).

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

## Performance experiment

To get consistent measurements, we select as many benchmarks and provenance tracers as we reasonably can, and run a complete matrix (every tracer on every benchmark).
@Tbl:machine describes our experimental machine.
We use BenchExec [@beyerReliableBenchmarkingRequirements2019] to precisely measure the CPU time, wall time, memory utilization, and other attributes of the process (including child processes) in a Linux CGroup without networking, isolated from other processes on the system.

\begin{table}
\caption{Our experimental machine description.}
\label{tbl:machine}
\begin{minipage}{\columnwidth}
\begin{center}
\scriptsize
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
\end{minipage}
\end{table}



## Benchmark subsetting

We implemented and ran many different benchmarks, which may be costly for future researchers seeking to evaluate new provenance systems.
Given the less-costly results of a small number of benchmarks, perhaps one predict the performance of the rest of the benchmarks.
We will try several methods to identify the most important benchmarks, keeping the ones which perform the best:

- **Principal component analysis (PCA) and K-means**.
  This is the traditional benchmark subsetting procedure evaluated by Yi et al. [@yiEvaluatingBenchmarkSubsetting2006].

  1. We form a matrix of all benchmarks by "observed features" of that benchmark.
     The observed features contain, for example, how many file open/closes per second, how many file metadata operations per second, etc.
     While not traditionally done, "the overhead ratio of this benchmark in that provenance engine" is a perfectly valid feature to consider.
     We only use features that are invariant when running the program twice (i.e., using operations per second, not total operations), so benchmarks which are functionally similar but run for a longer time to not consist different points than analogous shorter benchmarks.

  2. We apply PCA to that matrix.
     PCA is a mathematical procedure which combines a large number of "observed features" into smaller number "virtual features", linearly, while maximizing the amount of variance in the resulting "virtual space" (in a sense, spreading out the benchmarks as much as possible from each other).

  3. We apply K-means to the benchmarks in their reduced PCA-space.
     K-means is a fast clustering algorithm.
     Once the benchmarks are grouped into clusters, we identify one benchmark from each cluster to consist the benchmark subset.
   
- **Interpolative decomposition (ID)**.

  1. We form a matrix where each benchmark is a column, each provenance system is a row, and the elements contain the log of the overhead ratio from the provenance system to native.

  2. We apply ID to the matrix.
     ID seeks to estimate a $m \times n$ matrix by retaining $k$ of its columns and using a linear regression to estimate the remaining $n-k$ from those selected $k$ columns.
     Cheng et al. [@chengCompressionLowRank2005] give a $\mathcal{O}(k(m+n-k))$ algorithm for computing an optimal ID while keeping a reasonable[^reasonable-error] L2 norm of the difference between the estimated and actual columns.
     Cheng's procedure is implemented in `scipy.linalg.interpolative`[^scipy.linalg.interpolative].

    [^reasonable-error]: The best possible error for any rank-$k$ factorization of a matrix is given by the $(k+1)^{\mathrm{th}}$ singular value. Since ID constrains the space of permissible factors, the L2 loss will be at least that. Cheng et al.'s ID method guarantees an error within a $\sqrt{1 + k(min(m,n) - k)}$ factor of the $(k+1)^{\mathrm{th}}$ singular value. Read asymptotically, the bound asserts as the singular value decreases, so too does the L2 loss.

    [^scipy.linalg.interpolative]: See <https://docs.scipy.org/doc/scipy/reference/linalg.interpolative.html>

  3. We select the $k$ benchmarks corresponding to columns chosen by ID; these are the "best" $k$ columns which minimize the error when predicting the $n-k$ columns under a specific metric.

-  **Random search**.
    Random search proceeds like ID, but it selects $k$ benchmarks randomly.
    Like ID, it computes a linear predictor for the $m-k$ benchmarks based on the $k$ benchmarks.
    Then it evaluates the "goodness of fit" of that predictor, and repeats a fixed number of iterations, retaining the "best" $k$ benchmark subset.

Cross-validation proceeds in the following manner, given $m$ provenance systems, $n$ benchmarks, and $f$ features:

1. Separate 1 provenance system for testing from the $m-1$ provenance systems used for training.

2. Use the $(m-1) \times n$ training systems and $f \times n$ in one of the above algorithms to select the best $k < n$ benchmarks and compute predictors for the $n-k$ benchmarks.

3. Feed in the output of the $1 \times k$ testing provenance system on the selected $k$ benchmarks into the algorithm, and let the algorithm estimate the $n-k$ unselected benchmarks.

4. Score the difference between the algorithm's prediction of the test system on the $n-k$ unselected benchmarks and its actual performance.

5. Repeat to 1 until all systems have been used for testing.

Note that during cross-validation, testing data (used in step 4) must not be allowed to "leak" into the training phase (step 2).
For example, it would be invalid to do feature selection on all $m \times n$ data.
Cross-validation is supposed to simulate the situation where one is testing on *truly novel* data.

We will evaluate these methods based on cross-validated root mean square-error (RMSE).
Mean *square* error (MSE) preferable to mean *absolute* error (MAE) because it punishes outliers more.
Imagine a benchmark suite which minimizes MAE and another which minimizes MSE.
The MAE-minizing suite one might be very accurate for most provenance systems, but egregiously wrong for a few; a MSE-minizing suite may be "more wrong" on average, but the worst-case wouldn't be as bad as the MAE one.
As such, an MSE subset would be more practically useful for future publictions to benchmark their new provenance systems.

We score the model on its ability to predict the logarithm of the ratio between a program running in provenance-generating and native systems.
We use a ratio rather than the difference because some tests are very fast (10 seconds; so a 5 second predictive error matters a lot), while some tests are very slow (1000 seconds; so a 5 second predictive error matters very little).
We predict the logarithm of the ratio, rather than the ratio directly because the ratio is multiplicative.
Any real number is permissible; 0 indicates "nothing changed", 1 indicates a speedup by a certain factor, and -1 indicates a slowdown *by the same factor*.

While cross-validation does punish model-complexity and overfitting to some extent, we will still take the number of parameters into account when deciding the "best" model in the interest of epistemic modesty.
Preferring fewer parameters makes the model more generalizable on out-of-domain data, since even our full cross-validation data is necessarily incomplete.

## Performance model

A related problem to subsetting is inferring a performance model.
There are two motivations for inferring a performance model:

- A sysadmin may wish to provide a computational provenance capturing system to their institution, but getting approval to run new software on their system may be expensive (e.g., on highly secure systems, the sysadmin may need to acquire a security audit of the code before it can be approved for use).
  They may want to prospectively estimate the overhead of provenance collectors without having to install all the provenance collectors on their system, so they can select the optimal collector for their use-case.

- Inferring a provenance model may improve our understanding of the bottlenecks in provenance collectors.

A performance model should input features of a prospective workload and output the approximate overhead under different systems.
A priori, provenance systems put a "tax" on certain syscalls (e.g., file I/O operations, process forks, process execs), because the system has to intercept and record these
Therefore, we expect a low-dimensional linear model (perhaps number of I/O operations per second times a weight plus number of forks per second times another weight) would predict overhead optimally.
To estimate this, we use the following models:

- **Ordinary least-squares (OLS) linear regression**.
  We estimate the runtime of each benchmark on each provenance system as a linear regression of the features of each benchmark, learning weights for each feature in each provenance system using ordinary least-squares.
  This would create a model like $\mathrm{weight}_1 \cdot \mathrm{feature}_1 + \mathrm{weight}_2 \cdot \mathrm{feature}_2 + \cdots$
  However, we can reduced its number of paramters, and thereby increase its out-of-domain generalizability, by the next two methods.

- **Low-rank linear regression.**
  To further reduce the number of parameters, we apply singular value decomposition (SVD) to create lossily-compressed representation of the learned weights.
  TODO: describe this model

- **OLS on a subset of features.**
  This method proceeds like the OLS regression, except it only uses a subset of the features, ignoring the rest.
  This is like doing a LASSO regression, but with multiple linear predictors sharing the same set of features (LASSO is usually described as solving for just one linear predictor).
  Unfortunately, we do not know an efficient algorithm like ID for selecting this subset.
  We tried to algorithms: greedy, which picks one additional feature that decreases loss the most until it has $k$ features, and random, which selects a random $k$-sized subset.

We use as features:

- The number of \$x-syscalls made per walltime second, where \$x could be socket-related, file-related, reading-file-metadata, chmod, exec, clone, etc
- The number of syscalls per walltime second
- The amount of CPU time used per walltime second
- A constant fixed-cost per-execution

Like with benchmark minimization, we will use cross-validated RMSE errors in log of overhead ratio and the number of features in each model to select the best.

# Results

## Selected provenance collectors

@Tbl:tools shows the provenance collectors we collected and their qualitative features.
We did not try reproducing provenance systems for the following reasons:  [^DSK: I don't understand the prev sentence. this and the reasons below seem to switch between systems and collectors, but I'm not sure I understand if they are different ideas or just different words for the same thing. Could this be "The following issues led us not to reproduce certain collectors"?]

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
  
- **Kernel-level is out-of-scope (Hi-Fi, LPM/ProvMon, CamFlow).**  [^DSK: change to "Requires kernel changes"?]
  Kernel-space collectors are out-of-scope for this work due to their increased maintenance overhead, security risk, and difficulty of system administration.
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
  We tried to get this provenance system to run, with several weeks of effort: we emailed the original authors and other authors who used this system, and we left a GitHub issue describing the expected and actual results ^[See <https://github.com/dtg-FRESCO/opus/issues/1>]. However, we still could not get the system to run properly.
  If we had more time, perhaps we could debug the issue.  [^DSK: not sure this last sentence is useful - maybe drop it. Or change it to say something like ", in a reasonable time" at the end of the prior sentence.]

- **Needs more time (DTrace, SPADE, eBPF/bpftrace).**
  We simply needed more time to implement these provenance collectors.

- **Reproduced/excluded (ltrace).**
  ltrace is an off-the-shelf tool, available in most Linux package repositories.
  However, we found it could not handle several of our benchmark workloads.
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

The lack of source code availability, lack of up-to-date systems, and difficulty in setting up experimental infrastructure lead us to narrow our scope to studying only user-space provenance tracing, not kernel-space provenance tracing.

\begin{table}
\caption{Provenance collectors mentioned in primary and secondary studies in our search results.}
\label{tbl:tools}
%\begin{minipage}{\columnwidth}
\begin{center}
\scriptsize
\begin{tabular}{lll}
\toprule
Tool                                                               & Status                               \\
\midrule
strace                                                             & Reproduced                           \\
fsatrace                                                           & Reproduced                           \\
ReproZip \cite{chirigatiReproZipComputationalReproducibility2016}  & Reproduced                           \\
Sciunit2 \cite{tonthatSciunitsReusableResearch2017}                & Reproduced                           \\
rr \cite{ocallahanEngineeringRecordReplay2017}                     & Reproduced                           \\
CDE \cite{guoCDEUsingSystem2011}                                   & Reproduced                           \\
ltrace                                                             & Reproduced/excluded                  \\
SPADE \cite{gehaniSPADESupportProvenance2012}                      & Needs more time                      \\
DTrace \cite{DTrace}                                               & Needs more time                      \\
eBPF/bpftrace                                                      & Needs more time                      \\
OPUS \cite{balakrishnanOPUSLightweightSystem2013}                  & Not reproducible                     \\
CamFlow \cite{pasquierPracticalWholesystemProvenance2017}          & Kernel-level                         \\
Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}                   & Kernel-level                         \\
LPM/ProvMon \cite{batesTrustworthyWholeSystemProvenance2015}       & Kernel-level                         \\
RecProv \cite{jiRecProvProvenanceAwareUser2016}                    & No source                            \\
LPROV \cite{wangLprovPracticalLibraryaware2018}                    & No source                            \\
S2Logger \cite{suenS2LoggerEndtoEndData2013}                       & No source                            \\
ProTracer \cite{maProTracerPracticalProvenance2016}                & No source                            \\
FiPS \cite{sultanaFileProvenanceSystem2013}                        & No source                            \\
PANDDE \cite{fadolalkarimPANDDEProvenancebasedANomaly2016}         & No source                            \\
PASS/Pasta \cite{muniswamy-reddyProvenanceAwareStorageSystems2006} & No source                            \\
PASSv2/Lasagna \cite{muniswamy-reddyLayeringProvenanceSystems2009} & No source                            \\
Lineage FS \cite{sarLineageFileSystem}                             & No source                            \\
RTAG \cite{jiEnablingRefinableCrossHost2018}                       & No source                            \\
BEEP \cite{leeHighAccuracyAttack2017}                              & Requires HW                          \\
libdft \cite{kemerlisLibdftPracticalDynamic2012}                   & Requires HW                          \\
RAIN \cite{jiRAINRefinableAttack2017}                              & Requires HW                          \\
DataTracker \cite{stamatogiannakisLookingBlackBoxCapturing2015}    & Requires HW                          \\
MPI\cite{maMPIMultiplePerspective2017}                             & Requires recompilation               \\
LDX \cite{kwonLDXCausalityInference2016}                           & Requires recompilation               \\
Panorama \cite{yinPanoramaCapturingSystemwide2007}                 & VMs are too slow                     \\
PROV-Tracer \cite{stamatogiannakisDecouplingProvenanceCapture2015} & VMs are too slow                     \\
ETW \cite{EventTracingWin322021}                                   & Not for Linux                        \\
Sysmon \cite{markrussSysmonSysinternals2023}                       & Not for Linux                        \\
TREC \cite{vahdatTransparentResultCaching1998}                     & Not for Linux                        \\
URSprung \cite{rupprechtImprovingReproducibilityData2020}          & Not for Linux\footnotemark           \\
Ma et al. \cite{maAccurateLowCost2015}                             & Not for Linux                        \\
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

## Implemented benchmarks

\begin{table}
\caption{Benchmarks used in various provenance publications.}
\label{tbl:prior-benchmarks}
%\begin{minipage}{\columnwidth}
\begin{center}
\scriptsize
\begin{tabular}{p{0.21\linewidth}p{0.54\linewidth}p{0.12\linewidth}}
\toprule
Publication                                                  & Benchmarks                                                                                                                                      & Comparisons           \\
\midrule
TREC \cite{vahdatTransparentResultCaching1998}               & open/close, compile Apache, compile LaTeX doc                                                                                                   & Native                \\
PASS \cite{muniswamy-reddyProvenanceAwareStorageSystems2006} & BLAST                                                                                                                                           & Native ext2           \\
Panorama \cite{yinPanoramaCapturingSystemwide2007}           & curl, scp, gzip, bzip2                                                                                                                          & Native                \\
PASSv2 \cite{muniswamy-reddyLayeringProvenanceSystems2009}   & BLAST, compile Linux, Postmark, Mercurial, Kepler                                                                                               & Native ext3, NFS      \\
SPADEv2 \cite{gehaniSPADESupportProvenance2012}              & BLAST, compile Apache, Apache                                                                                                                   & Native                \\
Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}             & lmbench, compile Linux, Postmark                                                                                                                & Native                \\
libdft \cite{kemerlisLibdftPracticalDynamic2012}             & scp, {tar, gzip, bzip2} x {extract, compress}                                                                                                   & PIN                   \\
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
Sciunit \cite{tonthatSciunitsReusableResearch2017}           & VIC, FIE                                                                                                                                        & Native                \\
LPROV \cite{wangLprovPracticalLibraryaware2018}              & Apache, simplehttp, proftpd, sshd, firefox, filezilla, lynx, links, w3m, wget, ssh, pine, vim, emacs, xpdf                                      & Native                \\
MCI \cite{kwonMCIModelingbasedCausality2018}                 & Firefox, Apache, Lighttpd, nginx, ProFTPd, CUPS, vim, elinks, alpine, zip, transmission, lftp, yafc, wget, ping, procps                         & BEEP                  \\
RTAG \cite{jiEnablingRefinableCrossHost2018}                 & SPEC CPU 2006, scp, wget, compile llvm, Apache                                                                                                  & RAIN                  \\
URSPRING \cite{rupprechtImprovingReproducibilityData2020}    & open/close, fork/exec/exit, pipe/dup/close, socket/connect, CleanML, Vanderbilt, Spark, ImageML                                                 & Native, SPADE  \\
\bottomrule
\normalsize
\end{tabular}
\end{center}
%\end{minipage}
\end{table}
\footnotetext{LogGC measures the offline running time and size of garbage collected logs; there is no comparison to native would be applicable.}

Of these, @tbl:prior-benchmarks shows the benchmarks used to evaluate each tool, of which there are quite a few.
First, we eliminated several benchmarks from this set as non-starters for the reasons described in @tbl:excluded.
Then, we prioritized implementing frequently-used benchmarks, easy-to-implement benchmarks, and benchmarks that we believe have value in representing a computational science use-case.

- **HTTP/FTP servers/clients/traffic.**
  The most common benchmark class from prior work, HTTP servers/traffic, HTTP servers/clients, FTP servers/traffic, and FTP servers/clients are popular because prior work focuses overwhelmingly on provenance for the sake of security (auditing, intrusion detection, or digital forensics).
  Therefore, we implement HTTP servers with simulated traffic, HTTP servers with specific clients, and FTP servers with simulated traffic.
  Although we wanted to implement FTP servers with specific clients, all of those executions reach the callstack depth in ltrace, even when fetching a single file, so we had to drop those.
  We do not think they are substantially different from the FTP servers with simulated traffic.  [^DSK: is there value in FTP today, given how rarely it is still supported/permitted?]

- **Compiling packages.**
  Compiling packages from source is a common operation in computational science, so we implemented as many of these as we could and also implemented some of our own.
  However, compiling LLVM takes more than twice as long as the longest benchmark, so we excluded LLVM specifically from the benchmark suite.
  We implemented a pattern for compiling packages from Spack that discounts the time taken to download sources, counting only the time taken to unpack, patch, configure, compile, link, and install them.
  We try compiling Python, Boost, HDF5, glibc, Apache HTTPd, and Perl.
  In the future, we plan to implement compilation for more packages, in particular xSDK [@bartlettXSDKFoundationsExtremescale2017] packages.  [^DSK: not sure if this goes here or in Future Work/Conclusions.]

[^llvm]: Compiling LLVM from source takes multiple times longer than the longest benchmark. Since we already have many compilation benchmarks, we opted to increase the iteration counts (thereby reducing variance in our data) rather than include LLVM.

- **Browsers.**
  Implementing headless for browsers in "batch-mode" without GUI interaction is not impossibly difficult, but non-trivial.
  Furthermore, we deprioritized this benchmark because few computational science applications resemble the workload of a web browser.
  If we had more time, we would implement this benchmark too. [^DSK: not sure if this goes here or in Future Work/Conclusions.]

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

- **Coreutils and other utilities (bash, cp, ls, procps).**
  We did not see a huge representative value in these benchmarks that would not already be gleaned from lmbench, but due to its simplicity, we implemented it anyway.
  For `bash`, we do not know what workload prior works are using, but we test the speed of incrementing an integer and changing directories (`cd`).

- The rest of the programs are mostly specific desktop applications used only in one prior work.
  These would likely not yield any insights not already yielded by the benchmarks we implemented, and for each one we would need to build it from source, find a workload for it, and take the time to run it.
  They weigh little in the argument that our benchmark suite represents prior work, since they are only used in one prior work.
  We would like to implement these, but they have a lower priority. [^DSK: not sure if this goes here or in Future Work/Conclusions.]

\begin{table}
\caption{Benchmarks implemented by this work.}
\label{tbl:implemented-benchmarks}
%\begin{minipage}{\columnwidth}
\begin{center}
\scriptsize
\begin{tabular}{p{0.05\linewidth}p{0.24\linewidth}p{0.6\linewidth}}
\toprule
Prior works & This work                 & Benchmark group and examples from prior work                                                                   \\
\midrule
10          & yes (5/7 servers)         & HTTP server/traffic ({Apache httpd, miniHTTP, simplehttp, lighttpd, Nginx, tinyhttpd, cherokee} x apachebench) \\
9           & yes (3/4 clients)         & HTTP serer/client (simplehttp x {curl, wget, prozilla, axel})                                                  \\
8           & yes (3/5 orig + 4 others) & Compile user packages (Apache, LLVM, glibc, Linux, LaTeX document)                                             \\
5           & yes                       & FTP server/traffic (ProFTPd x ftpbench)                                                                        \\
8           & no                        & Browsers ({Firefox, Chromium} x Sunspider)                                                                     \\
5           & yes                       & Un/archive ({compress, decompress} x tar x {nothing, bzip2, pbzip, gzip, pigz, zip})                           \\
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

<!--
TODO: xSDK codes
-->

<!-- | 7 | Text-based browsers (w3m, lynx, elinks)                                                                              | Interactive                                           | -->
<!-- | 7 | TUI apps (Vim, nano, sysstat, mc, emacs, alpine, pine)                                                               | Interactive                                           | -->
<!-- | 6 | FTP client (lftp, yafc, tnftp, skod, AdvancedFTP, NetFTP)                                                            |                                                       | -->
<!-- | 5 | GUI apps (xpdf, Audacious, Sublime Text, Notepad++, Evince, Krusader, Mplayer, mpv, Transmission, FileZilla, Pidgin) | Interactive                                           | -->
<!-- | 1 | Windows programs (Notepad, Paint, IE)                                                                                | Wrong platform                                        | -->
<!-- | 1 | gif2png                                                                                                              | Unknown program (dozens of programs called "gif2png") | -->
<!-- | 1 | Vanderbilt                                                                                                           | Unknown program                                       | -->
<!-- | 1 | TextTransfer                                                                                                         | Unknown program                                       | -->
<!-- | 1 | DrawTool                                                                                                             | Unknown program                                       | -->
<!-- | 1 | yopsweb                                                                                                              | Unknown program                                       | -->

<!-- : Benchmarks rejected by this work {#tbl:rejected-bmarks} -->

## Subsetted benchmarks

## Quantitative performance comparison

## Predictive model

# Analysis

<!--
TODO: note that fsatrace has a hardcoded limit on the size of the buffer used to store file read/writes. If this size is exceeded, the program will exhibit undefined behavior. On my system, it crashes with a non-zero exit code but without any message.
-->
<!--
"CDE WARNING (unsupported operation): %s '%s' is a relative path and dirfd != AT_FDCWD\n",
-->

<!--
Active vs passive monitoring
Reprozip, Sciunit, RR, CDE vs strace, ltrace
-->

## Threats to validity

# Future work

# Conclusion

# References
