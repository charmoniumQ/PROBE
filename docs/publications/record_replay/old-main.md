The **same-architecture portability problem** is the problem of taking a program which works on one machine, transferring it to a different machine, and running it on that new machine without introducing any crashes.
<!-- Reframe this problem to be more specific, what does crash-freedom means? -->
In order to run the program, all of its dependencies have to be downloaded or recompiled for the other machine.
The program could have many dependencies, those can have dependencies, and the existence of a dependency might not be explicitly declared.
The dependency graph is often so complex, a concise list or specification is not readily available.
Note that the definition of portability does not include any kind of equivalence of results, just that the software can run without new crashes.
While higher-level reproducibility is the ultimate goal of this research area, same-architecture portability is a necessary condition along the way.

Some solutions to this problem are **user-level package managers** (Pip, Conda \cite{aaronmeurerCondaCrossPlatform2014}, Spack \cite{gamblinSpackPackageManager2015}, Nix \cite{bzeznikNixHPCPackage2017}, Guix \cite{valletPracticalTransparentVerifiable2022,courtesReproducibleUserControlledSoftware2015}, etc.) and **virtualization** (Docker, Vagrant, QEMU, VirtualBox, CharlieCloud \cite{priedhorskyCharliecloudUnprivilegedContainers2017}, Singularity \cite{kurtzerSingularityScientificContainers2017}).
Note, we will consider containerization as a virtualization, because it is a virtualization of Linux user-space, although it does not virtualize the kernel.
Both of these solutions require some additional effort from the user, when the user already installed their software stack locally.
1. For user-level package managers, they would have to write an environment description. If they use any software or software variants that are not packaged for that package manager, they may have to write package specifications too.
2. For virtualization, a user will either imperatively install the software in a virtual machine or declaratively write a script (Dockerfile, Vagrantfile, Singularity Definition File) which installs the software in a virtual machine.
Even if doing so would only take a few hours, many domain scientists are not willing to commit that amount of effort.
<!-- Add assumption that they didn't do from the start. -->

Another solution for the same-architecture portability of scientific computational experiments is **record/replay** (rr, CDE \cite{guoCDEUsingSystem2011}, ReproZip \cite{chirigatiReproZipComputationalReproducibility2016}, SciUnits \cite{tonthatSciunitsReusableResearch2017}), which requires almost no user-intervention.
In this scheme, record and replay are two programs where record runs a user-supplied program with user-supplied inputs and writes a **replay-package**, which contains all of the relevant data, libraries, and executables.
The replay-package can be sent to any machine that the replayer supports. The replayer runs the executable with the data and libraries from the replay-package.
The only user-intervention required to achieve same-architecture portability is that the user must (1) run their executable within the record tool and (2) upload the replay-package to a public location.
Some record/replay schemes aim to ensure bit-wise identical output <!-- of the entire program and --> of specific system calls which may otherwise be non-deterministic, especially as network calls and, random number generator calls; in that case, the replay-package would include a trace of those system calls, and the player would intercept and replay those system calls.
The downside of record/replay is that is has historically been slow.

This work uses a novel technique for recording in order to accelerate it.
The result will still solve the same-architecture portability problem with almost no user intervention.
We want to draw the attention of domain scientists who create computational scientific experiments and need a way to make those experiments executable.

A knock-on benefit of record/replay is that, depending on the technique, the replay-package will contain a record **computational provenance**.
Computational provenance is a record of what inputs went in to generating a specific computational artifact.
The First Provenance Challenge \cite{moreauSpecialIssueFirst2008} gives several examples where computational provenance data might be useful to a domain scientist.
For example, given several provenance records of the workflow described in Moreau,

* Find all atlas graphic images outputted from workflows where at least one of the input Anatomy Headers had an entry global \verb+maximum=4095+.

* Find all output averaged images of softmean (average) procedures, where the warp alignment used a 12th order non-linear model, i.e., softmean was preceded in file-based dataflow, directly or indirectly, by the command \verb+align_warp+ with argument \verb+-m 12+.

If collecting the provenance data is cheap, and already done for another goal (same-architecture portability), scientists can begin using that data to increase their productivity.

<!--
Applying library interpostion
Caveat: not as reproducible

Evaulation

-->
