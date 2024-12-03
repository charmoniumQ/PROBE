# Transparent, performant, non-privileged provenance tracing through library interposition

**Abstract**:

Provenance tracing is the idea of capturing the *provenance* of computational artifacts, (e.g., what version of the program wrote this file).
Prior work proposes recompiling with instrumentation, ptrace, and kernel-based auditing, which at best achieves two out of three desirable properties: transparency, performance, and non-privilege.

We present PROBE, a system-level provenance collector that uses library interpositioning to achieve all three.
We evaluate the performance of PROBE for scientific users.

# Introduction

**Provenance**

Provenance axes:

- **Service-**, ***Application-**, **workflow/language-**, **system-level**
- **Retrospective** vs **prospective provenance**

This work focuses on system-level, retrospective provenance (SLRP).

Always-on provenance: prov trace build and application

Some applications to motivate collection of SLRP.

SLRP provenance collector features:

- **Transparency**
- **Performance**
- **Non-privilege**: i.e., no changes to Linux boot parameters, no loading kernel modules, no use of privileged capacities, Why do we need this? Users on shared machines (e.g., HPC), security sensitive environments, users in containers
- Other key features:
  - **User-level** as opposed to kernel-level (non-privilege implies user-level, but not the converse)
  - **Completeness**

Methods of collecting SLRP:

- **Virtual machines**
- **Recompiling**
- **Binary instrumentation**
- **Kernel modification**
- **Kernel auditing frameworks**
- **Ptrace**
- **Library interposition**

_Outline of rest of work_

Contribution:
- Library interposition provenance collector called PROBE (Provenance for Replay OBservation Engine)
  - Note OPUS had one before us, but we do not believe OPUS is reproducible today.
- Performance analysis of provenance collectors
- Completeness analysis

# Prior work

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

Matrix:
- Each row is a group of prior works
- Each column is an SLRP collector-feature

# PROBE

- Procedure for determining functions to interpose
- What does the interposer actually do
- How to handle hardlinks and symlinks (inodes)
- How to handle cycles
- How to handle threads
- Interoperable output format

# Performance analysis

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

# Completeness analysis

- Compare theoretically and empirically with others
  - Library interposition trades off in completeness slightly.
    - We can detect and caution the user when they are tracing an application for which PROBE provenance collection may be incomplete
- Collecting provenance by itself is not the end goal; can PROBE provenance do some of the motivating applications mentioned above?

- **RQ2:** How does the provenance output of PROBE compare with prior provenance tracers (case studies)? Is it more complete or detailed?
  - Consider system-level provenance tracers separately from workflow-level and language-level provenance tracers
  - Cases: pile-of-scripts, standalone workflow, embedded workflow, C application, Python application, Jupyter Notebook
- **RQ3:** How faithfully can heuristics create a runnable package specification from a prov description?

# Threats to validity

# Conclusion

# Future work

- Improve completeness: static binary rewriting
- Improve performance
- Multi-node and HPC cases
