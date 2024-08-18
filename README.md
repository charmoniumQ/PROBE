# PROBE: Provenance for Replay OBservation Engine

This program executes and monitors another program, recording its inputs and outputs using `$LD_PRELOAD`.

These inputs and outputs can be joined in a provenance graph.

The provenance graph tells us where a particular file came from.

The provenance graph can help us re-execute the program, containerize the program, turn it into a workflow, or tell us which version of the data did this program use.

## Reading list

- [_Provenance for Computational Tasks: A Survey_ by Freire, et al. in  CiSE 2008](https://sci.utah.edu/~csilva/papers/cise2008a.pdf) for an overview of provenance in general.
- [_Transparent Result Caching_ by Vahdat and Anderson in USENIX ATC 1998](https://www.usenix.org/legacy/publications/library/proceedings/usenix98/full_papers/vahdat/vahdat.pdf) for an early system-level provenance tracer in Solaris using the `/proc` fs. Linux's `/proc` fs doesn't have the same functionality. However, this paper discusses two interesting application of provenance: unmake  (query lineage information) and transparent Make (more generally, incremental computation).
- [_CDE: Using System Call Interposition to Automatically Create Portable Software Packages_ by Guo and Engler in USENIX ATC 2011](https://www.usenix.org/legacy/events/atc11/tech/final_files/GuoEngler.pdf) for an early system-level provenance tracer. Their only application is software execution replay, but replay is quite an important application.
- [_Techniques for Preserving Scientific Software Executions: Preserve the Mess or Encourage Cleanliness?_ by Thain, Meng, and Ivie in 2015 ](https://curate.nd.edu/articles/journal_contribution/Techniques_for_Preserving_Scientific_Software_Executions_Preserve_the_Mess_or_Encourage_Cleanliness_/24824439?file=43664937) discusses whether enabling automatic-replay is actually a good idea. A cursory glance makes PROBE seem more like "preserving the mess", but I think, with some care in the design choices, it actually can be more like "encouraging cleanliness", for example, by having heuristics that help cull/simplify provenance and generating human readable/editable package-manager recipes.
- [_SoK: History is a Vast Early Warning System: Auditing the Provenance of System Intrusions_ by Inam et al. in IEEE Symposium on Security and Privacy 2023](https://adambates.org/documents/Inam_Oakland23.pdf) see specifically Inam's survey of different possibilities for the "Capture layer", "Reduction layer", and "Infrastructure layer". Although provenance-for-security has different constraints than provenacne for other purposes, the taxonomy that Inam lays out is still useful. PROBE operates by intercepting libc calls, which is essentially a "middleware" in Table I (platform modification, no program modification, no config change, incomplete mediation, not tamperproof, inter-process tracing, etc.).
- [_System-Level Provenance Tracers_ by me et al. in ACM REP 2023](./docs/acm-rep-pres.pdf) for a motivation of this work. It surveys prior work, identifies potential gaps, and explains why I think library interposition is a promising path for future research.
- [_Computational Experiment Comprehension using Provenance Summarization_ by Bufford et al. in ACM REP 2023](https://dl.acm.org/doi/pdf/10.1145/3641525.3663617) discusses how to implement an interface for querying provenance information. They compare classical graph-based visualization with an interactive LLM in a user-study.

## Installing PROBE

1. Install Nix with flakes. This can be done on any Linux (including Ubuntu, RedHat, Arch Linux, not just NixOS), MacOS X, or even Windows Subsystem for Linux.

   - If you don't already have Nix on your system, use the [Determinate Systems installer](https://install.determinate.systems/).

   - If you already have Nix (but not NixOS), enable flakes by adding the following line to `~/.config/nix/nix.conf` or `/etc/nix/nix.conf`:

     ```
     experimental-features = nix-command flakes
     ```

   - If you already have Nix and are running NixOS, enable flakes with by adding `nix.settings.experimental-features = [ "nix-command" "flakes" ];` to your configuration.

2. Run `nix env -i github:charmoniumQ/PROBE#probe-bundled`.

3. Now you should be able to run `probe record [-f] [-o probe_log] <cmd...>`, e.g., `probe record ./script.py --foo bar.txt`. See below for more details.

4. To view the provenance, run `probe dump [-i probe_log]`. See below for more details.

5. Run `probe --help` for more details.

## What does `probe record` do?

The simplest invocation of the `probe` cli is:

```bash
probe record <CMD...>
```

This will run `<CMD...>` under the benevolent supervision of libprobe, outputting the probe record to a temporary directory. Upon the process exiting, `probe` it will transcribe the record directory and write a probe log file named `probe_log` in the current directory.

If you run this again you'll notice it throws an error that the output file already exists, solve this by passing `-o <PATH>` to specify a new file to write the log to, or by passing `-f` to overwrite the previous log.

<!--
This is stuff that normal users don't need to know about. Developers may find it useful:

The transcription process can take some time (but usually no more than a few seconds unless disk IO is exceptionally slow) after the program exits, if you don't want to automatically transcribe the record, you can pass the `-n` flag, this will change the default output path from `probe_log` to `probe_record`, and will output a probe record directory that can be transcribed to a probe log later with the `PROBE transcribe` command, however the probe record format is not stable, users are strongly encouraged to have `PROBE record` automatically transcribe the record directory immediately after the process exits. If you do separate the transcription step from recording, then transcription **must** be done on the same machine with the exact same version of the cli (and other constraints, see the [section on serialization formats](https://github.com/charmoniumQ/PROBE/blob/main/probe_src/probe_frontend/README.md#serialization-formats) for more details).
-->


`probe record` does **not** pass your command through a shell, any subshell or environment substitutions will still be performed by your shell before the arguments are passed to `probe`. But it won't understand flow control statements like `if` and `for`, shell builtins like `cd`, or shell aliases/functions.

If you need these you can either write a shell script and invoke `probe record` on that, or else run:

```bash
probe record bash -c '<SHELL_CODE>'
```

(any flag after the first positional argument is treated as an argument to the command, not `probe`).

If you get tired of typing `probe record ...` in front of every command you wish to record, consider recording your entire shell session:

``` bash
$ probe record bash
bash$ ls -l
bash$ # do other commands
bash$ exit

$ probe dump
<dumps history for entire bash session> 
```

## What can I do with provenance?

That's a huge [work in progress](https://github.com/charmoniumQ/PROBE/pulls).

We're starting out with just "analysis" of the provenance. Does this input file influence that output file in the PROBEd process? Run


``` bash
nix shell nixpkgs#graphviz github:charmoniumQ/PROBE#probe-py-manual \
    --command sh -c 'python -m probe_py.manual.cli process-graph | tee /dev/stderr | dot -Tpng -ooutput.png /dev/stdin'
```

## Developing PROBE

1. Follow the previous step to install Nix.

2. Acquire the source code: `git clone https://github.com/charmoniumQ/PROBE && cd PROBE`

3. Run `nix develop`. This will leave you in a _Nix development shell_, with all the development tools you need to develop and build PROBE. It is like a virtualenv, in that it is isolated from your system's pre-existing tools. In the development shell, we all have the same version of Python with all the same packages. You can exit it by dyping `exit`.

4. From _within the development shell_, type `just compile`. This compiles the Rust, C, and generated-Python components. If you hack on either, run `just compile` again before continuing.

5. The manually-written Python scripts should already be added to the `$PYTHONPATH`. You should be able to edit them in place.

6. Run `probe <args...>` or `python -m probe_py.manual.cli <args...>` to invoke the Rust or Python code respectively.

## Prior art

- [RR-debugger](https://github.com/rr-debugger/rr) which is much slower, but features more complete capturing, lets you replay but doesn't let you do any other analysis.

- [Sciunits](https://github.com/depaul-dice/sciunit) which is much slower, more likely to crash, has less complete capturing, lets you replay but doesn't let you do other analysis.

- [Reprozip](https://www.reprozip.org/) which is much slower and has less complete capturing.

- [CARE](https://proot-me.github.io/care/) which is much slower, has less complete capturing, and lets you do containerized replay but not unpriveleged native replay and not other analysis.

- [FSAtrace](https://github.com/jacereda/fsatrace) which is more likely to crash, has less complete capturing, and doesn't have replay or other analyses.
