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
  We identify 45 provenance collectors from prior work, identify their method-of-operation, and reproduce the ones that meet specific criteria.
  We successfully reproduced 9 out of 16^[TODO: update with data] collectors that met our criteria.

- *A benchmark suite for system-level provenance collectors*:
  Prior work does not use a consistent set of benchmarks; often publications use an overlapping set of benchmarks from prior work.
  We find the superset of all benchmarks used in the prior work our rapid review identified, identify unrepresented areas, and find a statistically valid subset of the benchmark.
  Our benchmark subset is able to recover the original benchmark results within^[TODO: update with data] 25% of the acutal value 95% of the time, assuming errors are iid and normally distributed.

<!--
- *A quantitative performance comparison of system-level provenance collectors against this suite*:
  Prior publications often only compares the performance their provenance tool to the baseline, no-provenance performance, not to other provenance tools.
  It is difficult to compare provenance tools, given data of different benchmarks on different machines.
  We run a consistent set of benchmarks on a single machine over all provenance tools.
-->

- *We show that simple performance models are insufficient to capture the complexity of provenance collector overheads*:
  We use linear models for predicting the overhead of \$X application in \$Y provenance collector based on \$X application's performance characteristics (e.g., number of file syscalls per second).
  Despite trying linear regression, with and without rank reduction, with and without feature selection, our best model is still quite inaccurate, showing performance overhead of application \$X in provenance collector \$Y is not as simple as features of \$X times features of \$Y.
  
The remainder of the paper is structured as follows. [^RMM: Outline paper structure here.]

# Background

Provenance tools and data have many potential applications, including the following from Pimentel et al. [@pimentelSurveyCollectingManaging2019] and Sar and Cao [@sarLineageFileSystem]:

1. **Reproducibility**.
   A description of the inputs and processes used to generate a specific output can aid manual and automatic reproduction of that output[^acm-defns].
   Empirical studies [@trisovicLargescaleStudyResearch2022; @graysonAutomaticReproductionWorkflows2023; @collbergRepeatabilityComputerSystems2016; @zhaoWhyWorkflowsBreak2012] show that reproducibility is rarely achieved in practice, probably due to its difficulty under the short time budget that scientists have available to spend on reproducibility.
   If reproducibility was easier to attain, perhaps because of automatic provenance tracking, it may improve the reproducibility rate of computational research.
   Provenance data improves **manual reproducibility**, because users have a record of the inputs, outputs, and processes used to create a computational artifact.
   Provenance data also has the potential to enable **automatic reproducibility**, if the process trace is detailed enough to be "re-executed".
   This idea is also called "software record/replay".
   Automatic reproduciblity opens itself up to other applications to, like saving space by deleting results, and regenerating them on-demand.
   However, not all provenance collectors make this their goal.

   [^acm-defns]: "Reproduction", in the ACM sense, where a **different team** uses the **same artifacts** to generate the output artifact [@acminc.staffArtifactReviewBadging2020].

2. **Caching subsequent re-executions**.
   Computational science inquiries often involve changing some code and re-executing the workflows (e.g., testing different clustering algorithms).
   In these cases, the user has to keep track of what parts of the code they changed, and which process have to be re-executed.
   However, an automated system could read the computational provenance graphs produced by previous executions, look at what parts of the code changed, and safely decide what processes need to be re-executed.
   The dependency graph would be automatically deduced, leaving less chance for a dependency-misspecification, unlike Make and CMake, which require the user to manually specify a dependency graph.

3. **Comprehension**. 
   Provenance helps the user understand and document workflows and workflow results.
   An automated tool that consumes provenance can answer queries like "What version of the data did I use for this figure?" and "Does this workflow include FERPA-protected data?".
   A user might have run dozens of different versions of their workflow, and they may want to ask an automated system, "show me the results I previously computed based on that data with this algorithm?".

There are three high-level methods by which one can capture computational provenance: 1) by modifying an application to report provenance data, 2) by leveraging a workflow engine or programming language to report provenance data, and 3) by leveraging an operating system to emit provenance data to report provenance data [@freireProvenanceComputationalTasks2008].
Application-level provenance is the most semantically rich, but the least general, since it only applies to particular applications which have been modified to disclose provenance.
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

The implementation cost of adopting system-level provenance in a project which currently has no provenance is low because the user need not change _anything_ about their application or workflow;
  they merely need to install some provenance tracer onto their system and rerun their application.
Although the user may eventually use a more semantically rich provenance, low-initial-cost system-level provenance would get provenance's "foot in the door".
Since system-level provenance collection is a possibly valuable tradeoff between implementation cost and enabling provenance applications, system-level provenance will be the subject of this work.

In the context of system-level provenance, artifacts are usually files, processes, or strings of bytes.
Operations are usually syscalls involving artifacts, e.g., `fork`, `exec`, `open`, `close`.
For example, suppose a bash script runs a Python script that uses matplotlib to create a figure.
A provenance collector may record the events in @Fig:prov-example.

\begin{figure*}
\begin{center}
\subcaptionbox{
    Abridged list of events recorded by a hypothetical system-level provenance collector.
  }{
  \begin{minipage}{0.44\textwidth}
  \begin{enumerate}
    \item The user created a process, call it PID=1.
    \item The process PID=1 executed bash.
    \item The loader of process PID=1 loaded libc.so.6.
    \item The process PID=1 forked a process, call it PID=2.
    \item The process PID=2 executed python.
    \item The process PID=2 read matplotlib.py (script library).
    \item The process PID=2 opened database for reading and writing, which creates a new version of the node in th provenance graph.
    \item The process PID=2 wrote figure.png.
  \end{enumerate}
  \end{minipage}
}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Abridged graph of events recorded by a hypothetical system-level provenance collector.
  The arrows point in the direction of dataflow.
  Other authors use other conventions for what they render as nodes, edges, and arrow direction.
}{\includegraphics[width=0.5\textwidth]{prov-example.pdf}}
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
Even a minor overhead per I/O operation would become significant when amplified over the tens of thousands of I/O operations that a program might execute per second.
Prior publications in system-level provenance usually contains some benchmark programs to evaluate the overhead imposed by the system-level provenance tool.
However, the set of chosen benchmark programs are not consistent from one publication to another, and overhead can be extermely sensitive to the exact choice of benchmark, so these results are totally incomparable between publications.
Most publications only benchmark their new system against native/no-provenance, so prior work cannot easily establish which system-level provenance tool is the fastest.

## Prior work

Each result of our rapid review (@Tbl:tools) is an obvious prior work on provenance collection in general.
However, those prior works look at only one or maybe two competing provenance tools at a time.
To the best of our knowledge, there has been no global comparison of provenance tools.
ProvBench^[TODO: cite; also cite CARE] uses 3 provenance collectors (CamFlow, SPADE, and OPUS), but they are solely concerned with the differences betwen representations of provenance, not performance.

On the other hand, benchmark subsetting is a well-studied area.
This work mostly follows Yi et al. [@yiEvaluatingBenchmarkSubsetting2006] paper which evaluates subsetting methodologies and determine that dimensionality reduction and clustering is broadly a good strategy.
Phansalkar et al.^[TODO: Cite Subsetting the SPEC CPU2006 Benchmark Suite] apply dimensionality reduction and clustering to SPEC CPU benchmarks.

# Methods

## Rapid Review

We began a rapid review to identify the research state-of-the-art tools for automatic system-level provenance.

Rapid Reviews are a lighter-weight alternative to systematic literature reviews with a focus on timely feedback for decision-making.
Schünemann and Moja [@schunemannReviewsRapidRapid2015] show that Rapid Reviews can yield substantially similar results to a systematic literature review, albeit with less detail.
Although developed in medicine, Cartaxo et al. show that Rapid Reviews are useful for informing software engineering design decisions [@cartaxoRoleRapidReviews2018; @cartaxoRapidReviewsSoftware2020].

We conducted a rapid review with the following parameters:

- **Search terms**: "system-level AND provenance", "computational provenance"

- **Search engine**: Google Scholar

- **Number of results**:
  50 of both searches.
  This threshold is the point of diminishing returns, as no new collectors came up in the 40th – 50th results.

- **Criteria**:
  A relevant publication would center on one or more operating system-level provenance collectors that capture file provenance.
  A tool requiring that the user use a specific application or platform would be irrelevant.

## Benchmark Selection

Using the tools selected above, we identified all benchmarks that have been used in prior work.
We excluded benchmarks for which we could not even find the original program (e.g., TextTransfer), benchmarks that were not available for Linux (e.g., Internet Explorer), benchmarks with a graphical component (e.g., Notepad++), and benchmarks with an interactive component (e.g., GNU Midnight Commander).

We implemented the benchmarks as packages for the Nix package manager^[See https://nixos.org/guides/how-nix-works], so they are runnable on many different platforms.
Nix has official installers for Linux, Mac OS X, and Windows Subsystem for Linux on i686, x86_64, and aarch64 architectures, but FreeBSD and OpenBSD both package Nix themselves, and it can likely be built from source on even more platforms.

We also added new benchmarks:

<!--
- **Workflows**:
  Only one of the commonly used benchmarks from prior work (BLAST) resembles an e-science workflow (multiple intermediate inputs/outputs on the filesystem), so we added non-containerized Snakemake workflows from prior work [@graysonAutomaticReproductionWorkflows2023].
-->

- **Data science**:
  None of the benchmarks resembled a typical data science program, so we added the most popular Notebooks from Kaggle.com, a data science competition website.
  Data science is a good use-case for provenance collection because because a user might want have a complex data science workflow and want to know from what data a certain result derives, and if it a certain result used the latest version of that data and code.

- **Compilations**:
  Prior work uses compilation of Apache or of Linux.
  We added compilation of several other packages (any package in Spack) to our benchmark.
  Compiling packages is a good use-case for a provenance collection because a user might trial-and-error multiple compile commands and not remember the exact sequence of "correct" commands;
  the provenance tracker would be able to recall the commands which did not get overwritten, so the user can know what commands "actually worked". ^[DSK: this reminds me of VisTrails from Utah.]

<!--
- **Computational simulations**:
  High-performance computing (HPC) scientific simulations could benefit from provenance tracing.
  These HPC applications may have access patterns quite different than conventional desktop applications.
  The xSDK framework [@bartlettXSDKFoundationsExtremescale2017] collects a ^[DSK: end is missing]
-->

## Performance Experiment

To get consistent measurements, we select as many benchmarks and provenance tracers as we reasonably can, and run a complete matrix (every tracer on every benchmark) 3 times in a random order^[TODO: update with data].
@Tbl:machine describes our experimental machine.
We use BenchExec [@beyerReliableBenchmarkingRequirements2019] to precisely measure the CPU time, wall time, memory utilization, and other attributes of the process (including child processes) in a Linux CGroup without networking, isolated from other processes.
We disable ASLR, which does introduce non-determinism into the execution time, but it randomizes a variable that may otherwise have confounding effect [@mytkowiczProducingWrongData2009].
We restrict the program to a single core in order to eliminate unpredictable scheduling and prevent other daemons from perturbing the experiment (they can run on the other N-1 cores).
We wrap the programs that exit quickly in loops so they take about 10 seconds without any provenance system, isolating the cold-start costs.
While cold-start costs can be significant, if the total program execution time is small, the user may not notice even the highest overhead of provenance collectors.
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

- **Accuracy**.
   How closely do features of the subset resemble features of the original set?
   We will evaluate this by computing the root-mean squared error of a non-negative linear regression from the standardized features of selected benchmarks to the mean of features of the total set.

- **Representativeness.**
   How close are benchmarks in the original set to benchmarks in the subset?
   We will evaluate this by computing root mean squared error (RMSE) on the euclidean distance of standardized features from each benchmark in the original set to the closest benchmark in the selected subset.

We use a non-negative linear regression to account for the possibility that the total set has unequal proportions of benchmark clusters.
We require the weights to be non-negative, so doing better on each benchmark in the subset implies a better performance on the total.
Finally, we normalize these weights by adding several copies of the following an equation to the linear regression: $\mathrm{weight}_A + \mathrm{weight}_B + \dotsb = 1$.
Yi et al. [@yiEvaluatingBenchmarkSubsetting2006] were attempting to subset with SPEC CPU 2006, which one can assume would already be balanced in these terms, so their analysis uses an unweighted average.

We standardize the features by mapping $x$ to $z_x = (x - \bar{x}) / \sigma_x$.
While $x$ is meaningful in absolute units, $z_x$ is meaningful in relative terms (i.e., a value of 1 means "1 standard deviation greater than the mean").
Yi et al., by contrast, only normalize their features $x_{\mathrm{norm}} = x / x_{\max}$ which does not take into account the mean value.
We want our features to be measured relative to the spread of those features in prior work.

We score by RMSE over mean absolute error (MAE), used by Yi et al. [@yiEvaluatingBenchmarkSubsetting2006], because RMSE punishes outliers more.
MAE would permits some distances to be large, so long it is made up for by other distances are small.
RMSE would prefer a more equitable distribution, which might be worse on average, but better on the outliers.
We think this aligns more with the intent of "representativeness."

For features, we will use features that are invariant between running a program ten times and running it once.
This gives long benchmarks and short benchmarks which exercise the same functionality similar feature vectors.
In particular, we use:

1. The log overhead ratio of running the benchmark in each provenance collectors.
   We use the logarithm of the ratio, rather than the ratio directly because the logarithm is symmetric with respect to overshooting and undershooting.
   Suppose \$x provenance collector runs benchmark \$y1 twice as fast and benchmark \$y2 twice as slow; the average of the overhead would be $(2 + \frac{1}{2}) / 2 = 1.25$, whereas the average of the logarithms would be $\log 2 + \log \frac{1}{2} = \log 2 - \log 2 = 0$, meaning the 2x speedup "canceled out" the 2x slowdown on average). 
   Note that the arithmetic mean of logarithms of a value is equivalent to the geometric mean of the value.

2. The ratio of CPU time to wall time.

3. The number of syscalls in each category per wall time second, where the categories consist of socket-related syscalls, syscalls that read file metadata, syscalls that write file metadata, syscalls that access the directory structure, syscalls that access file contents, exec-related syscalls, clone-related syscalls, exit-related syscalls, dup-related syscalls, pipe-related syscalls, close syscalls, pipe-related syscalls, and chdir syscalls.

In order to choose the subset, we will try clustering (k-means and agglomerative clustering with Ward linkage\footnote{k-means and agglomerative/Ward both minimize within cluster variance, which is equivalent to minimizing our metric of "representativeness" defined earlier, although they minimize it in different ways: k-means minimizes by moving clusters laterally; Agglomerative/Ward minimizes by greedily joining clusters.}), preceded by optional dimensionality reduction by principal component analysis (PCA).
Once the benchmarks are grouped into clusters, we identify one benchmark from each of the $k$ clusters to consist the benchmark subset.
We will sweep across $k$.
<!--

- **K-means.** K-means [@macqueenMethodsClassificationAnalysis1965] greedily minimizes within-cluster variance, which is equivalent to the "representativeness" RMSE distance we want to minimize.
  Unfortunately, k-means can easily get stuck in local minima and needs to take the number of clusters, $k$, as a parameter.
  We use random restarts and initialize with k-means++ [@arthurKmeansAdvantagesCareful2007].

- **Agglomerative clustering (Ward linkage).**
  Agglomerative clustering [@wardjr.HierarchicalGroupingOptimize1963] greedily minimizes a certain metric from the bottom up.
  All data points start out as singleton clusters, and the algorithm joins the "best" two clusters repeatedly.
  The Ward Linkage is a metric that joins the pair of clusters resulting in the smallest within-cluster variance, which is exactly what "representativeness" RMSE distance wants to minimize.
  Agglomerative clustering can output hierarchical clusters, which may be useful in other contexts.
-->

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
  OLS requires a $n_{\mathrm{bmarks}} n_{\mathrm{feats}}$ parameters, but we can reduced its number of parameters, and thereby increase its out-of-domain generalizability, by the next two methods.

- **OLS compressed with SVD.**
  To further reduce the number of parameters, we apply singular value decomposition (SVD) to create a lossily-compressed representation of the learned weights.
  This model can be interpreted similarly to OLS, but using $k$ "hidden" features which are linear combinations of $n_{\mathrm{feats}}$ "visible" features, where $k$ is usually much less than $n_{\mathrm{feats}}$.
  SVD uses $n_{\mathrm{feats}}k + kn_{\mathrm{bmarks}}$ parameters.

- **OLS on a greedy/random subset of features.**
  This method proceeds like the OLS regression, except it only uses a subset of the features, ignoring the rest.
  We tried two algorithms: greedy, which picks one additional feature that decreases loss the most until it has $k$ features, and random, which selects a random $k$-sized subset, using $k n_{\mathrm{bmarks}}$ parameters.

We use the same features as in \Cref{benchmark-subsetting}, but with the addition of a constant term, for a provenance collectors which have a fixed startup cost.

We use k-fold cross-validation to estimate generalizability of the predictor.
While cross-validation does punish model-complexity and overfitting to some extent, we will still take the number of parameters into account when deciding the "best" model in the interest of epistemic modesty.
Preferring fewer parameters makes the model more generalizable on out-of-domain data, since even our full cross-validation data is necessarily incomplete.

<!--

Cross-validation proceeds in the following manner, given $n$ benchmarks and $f$ features.

1. Separate the $n$ benchmarks into $\alpha n$ "testing" benchmarks and $(1 - \alpha)n$ "training" benchmarks.

2. Learn to predict the log overhead ratio based on  $f$ features of each of the $(1-\alpha)n$ training benchmarks.

3. Using the model learned in the previous step, predict the log overhead ratio on $\alpha n$ testing benchmarks.

4. Compute the RMSE of the difference between predicted and actual.

5. Repeat to 1 with a different, but same-sized test/train split.

6. Take the arithmetic average of all observed RMSE; this is an estimate of the RMSE of the predictor on out-of-sample data.
-->

# Results

## Selected Provenance Collectors

@Tbl:tools shows the provenance collectors we collected and their qualitative features.
Because there are not many open-source provenance collectors in prior work, we also include the following tools, which are not necessarily provenance collectors, but may be adapted as such: strace, ltrace, fsatrace, and RR.
See \Cref{notable-provenance-collectors} for more in-depth description of each collector.
The second column shows the "collection method."
See \Cref{collection-methods} for their exact definition.

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
  
- **No source.**^[TODO: Evaluate this first, so  "no source" AND "requires kernel changes" would be classified as "no source". Future work may be able to reproduce collectors which require kernel changes (or VMs), but has no chance of reproducing collectors which have no source.]
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

- **Reproduced/rejected (ltrace, CDE).**
  These are provenance collectors that we could reproduce on some workloads but not others (see \Cref{note-on-failed-reproducibility}).
  Missing values would complicate the data analysis too much, so we had to exclude these from our running-time experiment.

- **Reproduced (strace, fsatrace, RR, ReproZip, PTU, Sciunit, CARE).**
  We reproduced this provenance collector on all of the benchmarks.

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
Sciunit \cite{phamUsingProvenanceRepeatability2013}                & tracing                      & Reproduced                 \\
PTU \cite{phamUsingProvenanceRepeatability2013}\footnote{TODO: udpate}     & tracing                      & Reproduced                 \\
CARE \cite{janinCAREComprehensiveArchiver2014}                     & tracing                      & Reproduced                 \\
CDE \cite{guoCDEUsingSystem2011}                                   & tracing                      & Reproduced/rejected        \\
ltrace                                                             & tracing                      & Reproduced/rejected        \\
SPADE \cite{gehaniSPADESupportProvenance2012}                      & audit, FS, or compile-time   & Needs more time            \\
DTrace \cite{DTrace}                                               & audit                        & Needs more time            \\
eBPF/bpftrace                                                      & audit                        & Needs more time            \\
SystemTap \cite{prasadLocatingSystemProblems2005}                  & audit                        & Needs more time            \\
Namiki et al. \cite{namikiMethodConstructingResearch2023}          & audit                        & Needs more time            \\
PROV-IO \cite{hanPROVIOOCentricProvenance2022}                     & lib. ins.                    & Needs more time            \\
OPUS \cite{balakrishnanOPUSLightweightSystem2013}                  & lib. ins.                    & Not reproducible           \\
CamFlow \cite{pasquierPracticalWholesystemProvenance2017}          & kernel ins.                  & Requires custom kernel     \\
Hi-Fi \cite{pohlyHiFiCollectingHighfidelity2012}                   & kernel ins.                  & Requires custom kernel     \\
LPM/ProvMon \cite{batesTrustworthyWholeSystemProvenance2015}       & kernel ins.                  & Requires custom kernel     \\
Arnold\footnote{TODO: Cite this}                                   & kern ins.                    & Requires custom kernel     \\
LPS \cite{daiLightweightProvenanceService2017}                     & kern ins.                    & Requires custom kernel     \\
RecProv \cite{jiRecProvProvenanceAwareUser2016}                    & tracing                      & No source                  \\
LPROV \cite{wangLprovPracticalLibraryaware2018}                    & kernel mod., lib. ins.       & No source                  \\
S2Logger \cite{suenS2LoggerEndtoEndData2013}                       & kernel mod.                  & No source                  \\
ProTracer \cite{maProTracerPracticalProvenance2016}                & kernel mod.                  & No source                  \\
FiPS \cite{sultanaFileProvenanceSystem2013}                        & FS                           & No source                  \\
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
<!-- First, we eliminated several benchmarks from this set as non-starters for the reasons described in @Tbl:excluded-bmarks. -->
We prioritized implementing frequently-used benchmarks, easy-to-implement benchmarks, and benchmarks that we believe have value in representing a computational science use-case.

- The most common benchmark classes from prior work are, **HTTP servers/traffic**, **HTTP servers/clients**, **FTP servers/traffic**, and **FTP servers/clients** are popular because prior work focuses overwhelmingly on provenance for the sake of security (auditing, intrusion detection, or digital forensics).
  While these benchmarks may not be specifically relevant for computational science workloads, we wanted to include them in our suite to improve our coverage of benchmarks used frequently in prior works.
  We implemented 5 HTTP servers (Apache, miniHTTP, Python's http.server, lighttpd, Nginx) running against traffic from Hey (successor to ApacheBench) and 2 HTTP clients (curl and Wget).
  We implemented 1 FTP server (ProFTPD) running against traffic from httpbench^[See <https://github.com/selectel/ftpbench>] and 3 FTP clients (curl, Wget, and lftp).

- **Compiling packages** from source is a common operation in computational science, so we implemented as many of these as we could and also implemented some of our own.
  However, compiling glibc and LLVM takes much longer than everything else in the benchmark suite, so we excluded LLVM and glibc.
  We implemented a pattern for compiling packages from Spack that discounts the time taken to download sources, counting only the time taken to unpack, patch, configure, compile, link, and install them.
  We implemented compiling Python, Boost, HDF5, Apache, git, and Perl.^[TODO: update with data.]

- Implementing headless for **browsers** in "batch-mode" without GUI interaction is not impossibly difficult, but non-trivial.
  Furthermore, we deprioritized this benchmark because few computational science applications resemble the workload of a web browser.

- **Archive** and **unarchiving** is a common task for retrieving data or source code.
  We benchmark un/archiving several archives with several compression algorithms.
  Choosing a compression algorithm may turn an otherwise I/O-bound workload to a CPU-bound workload, which would make the impact of provenance tracing smaller.
  We implemented archive and unarchiving a medium-sized project (7 MiB uncompressed) with no compression, gzip, pigz, bzip, and pbzip2.

- **I/O microbenchmarks** could be informative for explicating which I/O operations are most affected.
  Prior work uses lmbench [@mcvoyLmbenchPortableTools1996], which benchmarks individual syscalls, Postmark [@katcherPostMarkNewFile2005], which focuses on many small I/O operations (typical for web servers), IOR^[TODO: cite], H5bench^[TODO: cite] and BT-IO^[TODO: cite], which are specialized for parallel I/O on high-performance machines, and custom benchmarks, for example running open/close in a tight loop.
  Since we did not have access to a high-performance machine, we used lmbench and Postmark.
  We further restrict lmbench to the test-cases relevant to I/O and used by prior work.

- **BLAST** [@altschulBasicLocalAlignment1990] is a search for a fuzzy string in a protein database.
  However, unlike prior work, we split the benchmark into query groups described by Coulouris [@coulourisBlastBenchmark2016], since the queries have different performance characteristics:
  blastn (nucleotide-nucleotide BLAST), megablast (large numbers of query sequences) blastp (protein-protein BLAST), blastx (nucleotide query sequence against a protein sequence database), tblastn (protein query against the six-frame translations of a nucleotide sequence database), tblastx (nucleotide query against the six-frame translations of a nucleotide sequence database).

- Prior work uses several **CPU benchmarks**: SPEC CPU INT 2006 [@henningSPECCPU2006Benchmark2006], SPLASH-3 [@sakalisSplash3ProperlySynchronized2016], SPLASH-2^[TODO: cite] and HPCG^[TODO: cite].
  While we do not expect CPU benchmarks to be particularly enlightening for provenance collectors, which usually only affect I/O performance, it was used in three prior works, so we tried to implement both.
  SPLASH-3 is an updated and fixed version of the same benchmarks in SPLASH-2.
  However, SPEC CPU INT 2006 is not free (as in beer), so we could only implement SPLASH-3.

- **Sendmail** is a quite old mail server program.
  Mail servers do not resemble a computational science workload, and it is unclear what workload we would run against the server.
  Therfore, we deprioritized this benchmark and did not implement it.

- **VCS checkouts** are a common computational science operation.
  We simply clone a repository (untimed) and run `$vcs checkout $commit` for random commits in the repository.
  CVS does not have a notion of global commits, so we use Mercurial and Git.

- VIC, FIE, ImageML, and Spark are real-world examples of **Data processing** and **machine-learning workflows**.
  We would like to implement these, but reproducing those workflows is non-trivial; they each require their own computational stack.
  For FIE, in particular, there is no script that glues all of the operations together; we would have to read the publication [@billahUsingDataGrid2016] which FIE supports to understand the workflow, and write our own script which glues the operations together.

- We did not see a huge representative value in **coreutils and friends (bash, cp, ls, procps)** that would not already be gleaned from lmbench, but due to its simplicity and use in prior work, we implemented it anyway.
  For `bash`, we do not know what exact workload prior works are using, but we test the speed of incrementing an integer and changing directories (`cd`).

- The **other** benchmark programs are mostly specific desktop applications used only in one prior work.
  These would likely not yield any insights not already yielded by the benchmarks we implemented, and for each one we would need to build it from source, find a workload for it, and take the time to run it.
  They weigh little in the argument that our benchmark suite represents prior work, since they are only used in one prior work.

\begin{table}
\caption{Benchmarks implemented by this work. For brevity, we consider categories of benchmarks in \Cref{tbl:prior-benchmarks}}
\label{tbl:implemented-benchmarks}
%\begin{minipage}{\columnwidth}
\begin{center}
\small
\begin{tabular}{p{0.03\textwidth}p{0.03\textwidth}p{0.36\textwidth}}
\toprule
Prior works & This work                 & Benchmark group and examples from prior work                                                                   \\
\midrule
12          & yes                       & HTTP server/traffic                                                                                            \\
10          & yes                       & HTTP serer/client                                                                                              \\
10          & yes                       & Compile user packages                                                                                          \\
9           & yes                       & I/O microbenchmarks                                                                                            \\
9           & no                        & Browsers                                                                                                       \\
6           & yes                       & FTP client                                                                                                     \\
5           & yes                       & FTP server/traffic                                                                                             \\
5           & yes                       & Un/archive                                                                                                     \\
5           & yes                       & BLAST                                                                                                          \\
5           & yes                       & CPU benchmarks                                                                                                 \\
5           & yes                       & Coreutils + friends (bash, ls, procps)                                                                         \\
3           & yes                       & cp                                                                                                             \\
2           & yes                       & VCS checkouts                                                                                                  \\
2           & no                        & Sendmail                                                                                                       \\
2           & no                        & Machine learning workflows (CleanML, Spark, ImageML)                                                           \\
1           & no                        & Data processing workflows (VIC, FIE)                                                                           \\
1           & no                        & RUBiS                                                                                                          \\
1           & no                        & x264                                                                                                           \\
1           & no                        & mysqld                                                                                                         \\
1           & no                        & gocr                                                                                                           \\
1           & no                        & Memcache                                                                                                       \\
1           & no                        & Redis                                                                                                          \\
1           & no                        & php                                                                                                            \\
1           & no                        & pybench                                                                                                        \\
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
  TODO: use the exact same label names as \Cref{tbl:implemented-benchmarks}.
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

1. The features are already standardized, so PCA has little to offer other than rotation and truncation.
   However, the truncation is throwing away potentially useful data.
   Since we have a large number of benchmarks, and the space of benchmarks is quite open-ended, the additional dimensions that PCA trims off appear be important for separating clusters of data.

2. K-means and agglomerative clustering yield nearly the same results.
   They both attempt to minimize within-cluster variance, although by different methods.

3. RMSE of the residual of linear regression will eventually hit zero because the $k$ exceeds the rank of the matrix of features by benchmarks;
   The linear regression has enough degrees of freedom to perfectly map the inputs to their respective outputs.

It seems that agglomerative clustering with $k=20$ has quite good performance, and further increases in $k$ exhibit diminishing returns.
At that point, the RMSE of the linear regression is about 1.12.
Assuming the error is iid and normally distributed, we can estimate the standard error of the approximation of the total benchmark by linear regression is about 0.12 (log-space) or $e^{0.12} \approx 1.12$ (real-space).
Within the sample, 68% of the data falls within one standard error (either multiplied or divided by a factor of 1.12x) and 95% of the data falls within two standard errors (a factor of $e^{2 \cdot 0.12}$ or 1.25x).
We examine the generated clusters and benchmark subset in @Tbl:members and @Fig:dendrogram.

\begin{figure*}
\subcaptionbox{
  Benchmark subset, where color shows resulting clusters.
  The same-color small dots are benchmarks in the same cluster, the ``x'' of that color is their hypothetical benchmark with their average features, and the big dot of that color is the closest actual benchmark to the average of their features.
  A benchmark subset replaces each cluster of small dots with just the single big dot.
}{
  \includegraphics[width=0.45\textwidth]{generated/pca0.pdf}
  \label{fig:benchmark-clusters}
}
\hspace{0.03\textwidth}%
\subcaptionbox{
  Benchmark subset, where color shows benchmark class (see \Cref{tbl:implemented-benchmarks}).
  For example, archive-with-gzip and archive-with-bzip2 are two benchmarks of the same type, and therefore color.
  The ``x'' still shows a posteriori cluster centers as in \Cref{fig:benchmark-clusters}.
}{
  \includegraphics[width=0.45\textwidth]{generated/pca1.pdf}
  \label{fig:benchmark-groups}
}
\caption{Benchmarks, clustered agglomeratively into 20 subsets using standardized performance features. These axes show only two dimensions of a high-dimensional space. We apply PCA \emph{after} computing the clusters, in order to project the data into a 2D plane.}
\label{fig:benchmark-pca}
\end{figure*}

@Fig:benchmark-clusters 
shows the a posteriori clusters with colors.
@Fig:benchmark-groups shows a priori benchmark "types", similar but more precise than those in @Tbl:implemented-benchmarks.
From these two, we offer the following observations:

1. It may appear that the algorithm did not select the benchmark closest to the cluster center, but this is because we are viewing a 2D projection of a high-dimensional space, like how three stars may appear next to each other in the sky, but in reality one pair may be much closer than the other, since we cannot perceive radial distance to each star.

2. Many of the clusters are singletons, for example the `python http.server` near $(5,6)$; this is surprising, but given there are not any other points nearby, it seems reasonable.

3. We might expect that benchmarks of the same type would occupy nearby points in PCA space, but it seems they often do not.
  lmbench is particularly scattered with points at $(-1, 0)$ and $(0, 5)$, perhaps because it is a microbenchmark suite where each microbenchmark program tests a different subsystem.

4. Postmark is intended to simulate the file system traffic of a web server (many small file I/O).
   Indeed the Postmark at $(4, -2)$ falls near several of the HTTP servers at $(4, -2)$ and $(6, -2)$.
   Copy is also similar.

\begin{figure}
\begin{center}
\includegraphics[width=0.48\textwidth]{generated/dendrogram.pdf}
\caption{
  Dendrogram showing the distance between clusters.
  A fork at $x = x_0$ indicates that below that threshold of within-cluster variance, the two children clsuters are far away enough that they should be split into two; conversely, above that threshold they are close enough to be combined.
  We label each cluster by their ``selected benchmark.''
  If there is a colon and a number after the name, it indicates the number of benchmarks contained in that cluster.
  Otherwise, the cluster is a singleton.
}
\label{fig:dendrogram}
\end{center}
\end{figure}

\begin{table}
\begin{center}
\scriptsize
\begin{tabular}{p{0.11\textwidth}p{0.05\textwidth}p{0.25\textwidth}}
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
\end{tabular}
\normalsize
\caption{
  A table showing cluster membership and weights.
  The weights show one way of approximating the features in the original set, which is by multiplying the features of the cluster representative by the weight and summing over all clusters.
}
\label{tbl:members}
\end{center}
\end{table}

To elucidate the structure of the clusters, we plotted a dendrogram (@Fig:dendrogram) and listed the members of each cluster (@Tbl:members).
We offer the following observations:

1. Fork and exec are close in feature-space, probably because programs usually do both.

2. cd and shell-echo are near each other.
   I is surprising that blastn is also near cd and shell-echo, but they both have similar cputime-to-walltime ratios.

3. Many of the CPU-heavy workloads are grouped together, under lm-protection-fault.

4. Many of the un/archive benchmarks are grouped together with lighttpd, which also accesses many files.

### Our suggestion

The programs in lmbench have very different performance characteristics (see @Fig:benchmark-groups).
Due to their simplicity, their results are interpretable (e.g., testing latency of `open()` followed by `close()` in a tight loop).
We report the total time it takes to run a large number of iterations[^lmbench-usage], rather than latency or throughput, in order to be consistent with benchmarks for which latency and throughput are not applicable terms.
If one has to run part of lmbench, it is not too hard to run all of lmbench.

[^lmbench-usage]: Users should set the environment variable `ENOUGH` to a large integer, otherwise lmbench will choose a number of iterations based on the observed speed of the machine which can vary between runs.

One should also include an application that does _some_ CPU processing but manipulats many small files like Postmark.
One need not go through the trouble of setting up Nginx, and although Apache appears a cluster representative, that cluster is also similar to Postmark.

TODO: Write more once we have better results.

There is an old adage, \emph{the best benchmark is always the target application}.
Benchmarking lmbench reveals how well certain aspects of performance, but benchmarking the target application reveals one the _actual_ performance.
If we may hazard a corollary, we might say, \emph{the second best benchmark is one from the target domain}.
Supposing one doens't know the exact application or inputs their audience will use, selecting applications from that domain is the next best option.
This is why we are surprised why such a large domain, computational science, is underrepresented in benchmarks in prior work.
Future work on system-level provenance for computational science should of course use a computational science benchmark, such as BLAST, compiling programs with Spack, or a workflow, whether or not they are selected by this clustering analysis.
Likewise, work on security should include HTTP servers.

## Predictive Model

\begin{figure}
\begin{center}
\includegraphics[width=0.49\textwidth]{generated/predictive-performance.pdf}
\caption{Competition between predictive performance models. Pure linear regression only has one instance with $n_{\mathrm{feats}} \times n_{\mathrm{bmarks}}$ parameters; the others have with varying numbers of parameters.}
\label{fig:predictive-performance}
\end{center}
\end{figure}

@Fig:predictive-performance shows us the competition between predictive performance models.
We observe the following:

- When the number of parameters is large, all of the algorithms preform similarly;
  Even though greedy feature selection is more constrained than low-rank matrix factorization (every solution found by greedy is a candidate used by low-rank, but not vice versa), there are enough degrees of freedom to find similar enough candidates.

- Linear regression has equivalent goodness-of-fit to matrix factorization with a high $k$, as expected.
  When the compression factor is low, the compressed version is just as good as the original.

- Random-best usually does not do better than greedy feature selection.
  However, greedy is much easier to compute.
  Greedy is not necessarily optimal, but our problem domain may lack the complexity to generate these cases.

Greedy feature selection with 20 parameters (predicting the performance on 5 systems using only $k = 4$ of 16 features) seems to preform the best in cross-validation.
Assuming the errors are iid and normally distributed, we find the standard error is about 0.95 in log-space or $e^{0.95} \approx 2.6$ in real-space.
Within the sample, 68% of the data falls within a factor of 2.6 (one standard error) and 95% falls within a factor of $e^{2 \cdot 0.95} \approx 6.7$, which is quite bad.
We view this result as saying, the performance overhead of provenance collectors is not easily predictable, even given our features (including the syscall-rates) of the program.

<!--
On 19 out of 20 cross-validation splits, greedy feature selection with $k=4$ chose the parameters in @Tbl:params.

\begin{table}
\begin{center}
\scriptsize
\begin{tabular}{p{0.04\textwidth}p{0.09\textwidth}p{0.09\textwidth}p{0.09\textwidth}p{0.09\textwidth}}
\toprule
 & metadata-reads per walltime second & constant fraction & cputime / walltime & execs-and-forks per walltime second \\
\midrule
fsatrace & 0.000003 & -0.001236 & -0.024958 & 0.000064 \\
noprov & 0.000000 & 0.000000 & 0.000000 & 0.000000 \\
reprozip & 0.000043 & -0.027311 & 0.266969 & 0.000438 \\
rr & 0.000021 & -0.011208 & 0.404307 & 0.000878 \\
strace & 0.000029 & -0.002243 & 0.229129 & 0.000312 \\
\bottomrule
\end{tabular}
\caption{Linear regression, using benchmark subset to approximate the original benchmark.}
\label{tbl:params}
\end{center}
\end{table}

For example to estimate the overhead of fsatrace, we would use the first row of @Tbl:params,

\small

$$\begin{array}{rl}
\log \frac{\mathrm{walltime}_{\mathrm{fsatrace}}}{\mathrm{walltime}_{\mathrm{noprov}}} =
& 3 \times 10^{-6} \qty(\frac{\mathrm{metadata\ reads}}{\mathrm{walltime}_{\mathrm{noprov}}})
- 0.001 \cdot \qty(\frac{1}{\mathrm{walltime}_{\mathrm{noprov}}}) \\
& - 0.02 \cdot \qty( \frac{\mathrm{cputime}_\mathrm{noprov}}{\mathrm{walltime}_{\mathrm{noprov}}})
+ 6 \times 10^{-5} \cdot \qty(\frac{\mathrm{execs\ and\ forks}}{\mathrm{walltime}_{\mathrm{noprov}}}) \\
\end{array}$$

\normalsize

-->

<!-- TODO: consider a non-negative linear regression -->

<!--
The system calls features can be observed using strace.
The CPU time and wall time of noprov can be observed using GNU time.
One need not complete an entire execution to observe the these fatures; one merely needs to record the features until they stabilize (perhaps after several iterations of the main loop).
-->

## Discussion

**Prior work focuses on security, not computational science.**
@Tbl:implemented-benchmarks shows the top-used benchmarks are server programs, followed by I/O benchmarks.
Server programs access a lot of small files, with concurrency, which is a different file-access pattern than scientific applications.
BLAST (used by 5 / 29 publications with benchmarks, see @Tbl:prior-benchmarks) is the only scientific program to be used as a benchmark by more than one publication.
Benchmark subsetting includes two^[TODO: update with data] different BLAST programs, because they are sufficiently different than the rest.

One difference between security and computational science is that security-oriented provenance collectors have to work with adverserial programs:
there should be no way for the program to circumvent the provenance tracing, e.g. `PTRACE_DETACH`.
Computational science, on the other hand, may satisfied by a solution that *can* be intentionally circumvented by an uncooperative program, but would work most of the time, provided it can at least detect when provenance collection is potentially incomplete.
Interposing standard libraries, although circumventable, has been used by other tools [@xuDXTDarshanEXtended2017].

<!--
**Prior work on provenance collectors doesn't test on many workflows.**
Workflows, for the purposes of this discussion, are programs that are structured as a set of loosely coupled components whose execution order is determined by dataflow.
Workflows are important for computational science, but also other domains, e.g., online analytical processing (also known as OLAP).
Under this definition, non-trivial source-code compilation is a workflow.
-->

**Provenance collectors vary in power and speed, but fast-and-powerful could be possible.**
While all bear the title, provenance collector, some are **monitoring**, merely recording a history of operations, while others are **interrupting**, interrupt the process when the program makes an operation.
Fsatrace, Strace, and Ltrace are monitoring, while ReproZip, Sciunit, RR, CARE, and CDE are interrupting, using their interruption store a copy of the files that would be read or appended to by the process.
We expect the monitoring collectors to be faster than the interrupting collectors, but the performance of strace is not that far off of the performance of RR^[TODO: updaet with data.].
Strace and RR both use ptrace, but strace does very little work while RR maintains may need to intercept and reinterpret the syscall, (see treatment of `mmap` in RR's publication [@ocallahanEngineeringRecordReplay2017]).
This suggests most of the overhead actually be due to `ptrace` and its incurred context switches.
None of the interrupting provenance collectors use library interposition or eBPF.
Perhaps a faster underlying method would allow powerful features of interrupting collectors in a reasonable overhead budget.

**Provenance collectors are too slow for "always on".**
One point of friciton when using system-level provenance collection is that users have to remember to turn it on, or else the system is useless.
There may be advantage to be found in "always on" provenance system; for example, a user might change their login shell to start within a provenance collector.
Unfortunately, the conventional provenance collectors exhibit an intolerably high overhead to be used always, with the exception of fsatrace.
fsatrace is able to so much faster because it uses library interpositioning rather than ptrace (see "fast-and-powerful" discussion above), but fsatrace is one of the weakest collectors; it only collects file reads, writes, moves, deletes, queries, and touches (nothing on process forks and execs).

**The space of benchmark performance in provenance systems is highly dimensional.**
The space of benchmarks is naturally embedded in a space with features as dimensions.
If there were many linear relations between the features (e.g., CPU time per second = 1 - (file syscalls per second) * (file syscall latency)), then we would expect clustering to reveal fewer clusters than the number of features.
Indeed, there are somewhat fewer clusters than the number of features (20 &lt; 21)^[TODO: update with data], it seems that most dimensions are not redundant or if they are, their redundancy is not expressible as linear relationship.
This complexity is also present when trying to predict performance as a function of workload features; either the relationship is non-linear, or we are missing a relevant feature.

**Computational scientists may already be using workflows.**
While system-level provenance is the easiest way to get provenance out of many applications, if the application is already written in a workflow engine, such as Pegasus^[TODO: cite], they can get provenance through the engine.
Computational scientists may move to workflows for other reasons, because workflows make it easier to parallelize code on big machines and integrate loosely coupled components together.
That may explain why prior work on system-level provenance focuses more on security applications.

## Threats to Validity

**Internal validity**:
We mitigate measurement noise by:
- Isolating the sample machine \Cref{performance-experiment}
- Running the code in cgroups with a fixed allocation of CPU and RAM
- Rewriting benchmarks that depend on internet resources to only depend on local resources
- Averaging over 3^[TODO: update] iterations helps mitigate noise.
- Randomizing the order of each pair of collector and benchmark within each iteration
We use cross-validation for the performance model

**External validity**:
When measuring representativeness of our benchmark subset we use other characteristics of the workload, not just performance in each collector.
Therefore, our set also maintains variety and representativeness in underlying characteristics, not just in the performance we observe.
Rather than select the highest cluster value, we select the point of diminishing return, which is more likely to be generalizable.

Regarding the performance model, we use cross-validation to asses out-of-sample generalizability.

<!--
**Construct validity**:
We defined "subset representativeness" as the RMSE of euclidean distance between each benchmark and its closest selected benchmark in feature space.
We think this definition is valid because it takes into account closeness in observed performance and underlying characteristics, and it sufficiently punishes outliers.
We defined "subset accuracy" as the RMSE between a function of the subset results and the total set's results.
If the total set can be predicted based on a subset, than the total set delivers no "new" information, and indicates that the subset is useful as a benchmark suite.
Finally, we defined "accuracy of performance prediction" as RMSE of distance between each benchmark and a function of its a priori features.
-->

# Future Work

In the future, we plan to implement compilation for more packages, in particular xSDK [@bartlettXSDKFoundationsExtremescale2017] packages.
Compilation for these packages may be different than Apache and Linux because xSDK is organized into many dozens of loosely related packages.
We also plan to implement computational workflows.
Workflows likely have a different syscall access pattern unlike HTTP servers because the files may be quite large, unlike `cp` because workflows have CPU work blocked by I/O work, and unlike archiving because there are multiple "stages" to the computation.

We encourage future work that implements interrupting provenance collector using faster methods like library interposition or eBPF as opposed to `ptrace`.
Between them, there are pros and cons: eBPF requires privileges, but could be exposed securely by a setuid/setgid binary; library interposition assumes the tracee only uses libc to make I/O operations.
None of the interrupting collectors we know of exploit it, some of the interruption work may be "postponed";
if a file is read, it can be copied at any time unless/until it gets mutated ("copy-on-write-after-read").
Other reads can be safely copied after the program is done, and new file writes obviously do not need to be copied at all.
Perhaps the performance overhead would be low enough to be "always on", however storage and querying cost need to be dispatched with as well.

# Conclusion

We hope this work serves as a part of a bridge from research to practical use of provenance collectors.
As such, we address practical concerns of a user wanting to use a provenance collector.
We identify the reproducible and usable provenance collectors from prior work, and we evaluate their performance on synthetic and real-world workloads.

\appendix

# Collection methods

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

# Table of benchmarks by prior publication

See @Tbl:prior-benchmarks for a list of prior publications and what benchmarks they use, if, for example, one wishes to see the original contexts in which Firefox was used.

\begin{table}[h]
\caption{Benchmarks used by prior works on provenance collectors (sorted by year of publication).}
\label{tbl:prior-benchmarks}
%\begin{minipage}{\columnwidth}
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
Arnold\footnote{TODO: Citation}                              & cp, CVS checkout, make libelf, LaTeX, Apache, gedit, Firefox, spreadsheet, SPLASH-2                                                             & Native                \\
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
%\end{minipage}
\end{table}
\footnotetext{LogGC measures the offline running time and size of garbage collected logs; there is no comparison to native would be applicable.}

# Short description of notable provenance collectors

- **CDE** is a record/replay tool proposed by Guo and Engler [@guoCDEUsingSystem2011].
  During record, CDE  uses `ptrace` to intercept its syscalls, and copy relevant files into an archive.
  During rerun, can use `ptrace` to intercept syscalls and redirect them to files in the archive.
  PTU uses a modified version of CDE that works on all of our benchmarks, so we can use that as a proxy.

- **ltrace** similar to strace, but it traces dynamic library calls not necessarily syscalls.
  It still uses `ptrace`.

- **strace** is a well-known system program that uses Linux's `ptrace` functionality to record syscalls, their arguments, and their return code to a file.
  strace even parses datastructures to write strings and arrays rather than pointers.
  In this work, we use an strace configuration that captures all file-related syscalls but read/write[^read/write], file-metadata realated syscalls, socket- and IPC- related sycalls but send/recv, and process-related syscalls.

  [^read/write]: We do not need to capture individual reads and writes, so long as we capture that the file was opened for reading/writing.

- **fsatrace** reports file I/O using library-interpositioning, a technique where a program mimics the API of a standard library.
  Programs are written to call into the standard library, but the loader sends those calls to the interpositioning library instead.
  The interpositioning library can log the call and pass it to another library (possibly the "real" one), so the program's functionality is preserved.
  This avoids some context-switching overhead of `ptrace`, since the logging happens in the tracee's process.

- **CARE** is a record/replay tool inspired by CDE.
  However, CARE has optimizations enabling it to copy fewer files, and CARE archives can be replayed using `chroot`, `lxc`, or `ptrace` (by emulating `chroot`); CDE only supports `ptrace`, which is slower than the other two.

- **RR** [@ocallahanEngineeringRecordReplay2017] is a record/replay tool.
  It captures more syscalls than just file I/O, including `getrandom` and `clock_gettime` and it is able to replay its recordings in a debugger.
  Where other record/replay tools try to identify the relevant files, RR only memorizes the responses to each syscall, so it can only replay that exact code path.
  CDE, CARE, ReproZip, PTU, and Sciunit allow one to replay a different binary or supply different inputs in the filesystem of an existing recording.

- **ReproZip** is a record/replay inspired by CDE.
  ReproZip archives can be replayed in Vagrant, Docker, Chroot, or natively.
  Unlike other record/replay tools, ReproZip explicitly constructs the computational provenance graph.

- **PTU** (Provenance-To-Use) is an adaptation of CDE which explicitly constructs the computational provenance graph.

- **Sciunit** is a wrapper around PTU that also applies block-based deduplication.

# Note on failed reproducibility


While we could run **ltrace** on some of our benchmarks, it crashed when processing on the more complex benchmarks.
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

**CDE** can run some of our benchmarks, but crashes when trying to copy from the tracee process to the tracer due to `ret == NULL`[^cde-note]:

\scriptsize

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

# References
