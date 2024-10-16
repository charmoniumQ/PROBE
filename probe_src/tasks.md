Core functionality:
- [ ] Ensuring libprobe works
  - [x] Debug why libprobe doesn't work with Python. Sam fixed this.
  - [x] Debug pthreads not making graph.
  - [x] Debug `createFile.c` crash while trying to `mkdir_and_descend`.
  - [x] Debug `gcc`.
  - [x] Add thread ID and pthread ID to op.
  - [ ] Don't use libc structs directly. Copy out the relevant data to a libprobe-owned struct.
  - [ ] Check that various versions of glibc and various versions of musl have the same offsets for the relevant data in the libc structs described above.

- [x] Implement Rust CLI for record. Jenna finished this.
  - The Rust wrapper should replace the functionality of `record` in the `./probe_py/cli.py`. It should output a language-neutral structure that can be parsed quickly later on.
  - [x] The Rust wrapper should exec the program in an environment with libprobe in `LD_PRELOAD`.
  - [x] The Rust wrapper should transcribe the C structs into a language-neutral format.
  - [x] Split "transcribing" from "running in PROBE". We should be able to do them in two steps.
  - [x] Parse the language-neutral format into a `ProvLogTree` in Python, replacing `./probe_py/parse_probe_log.py`.
  - [x] Make sure analysis code still runs.
  - [x] Get GDB working.
  - [x] Compile statically.

- [ ] Generate a replay package (see branch generate-replay-package). Sam is working on this
  - [ ] Should be activated by a flag: `./PROBE record --capture-files`
  - [ ] Should copy all read files into the probe log.
  - [ ] Should export the PROBE log to the following formats with a CWL script:
    - [ ] [OCI image](https://opencontainers.org/) (runnable with Docker)
      - [ ] Test that executing this image produces the same stdout, stderr, and files for the tests we already have.
    - [ ] Tar-ball intended for chroot
    - [ ] Directory
    - [ ] VM image.
      - [ ] Test execution again.
    - [ ] Research ways to speed up the recording phase.

- [ ] Persistent provenance
  - Provenance graph should get stored in user-wide directory.
  - It should be SQLite.

Core tests:
- [x] Write end-to-end-tests. End-to-end test should verify properties of the NetworkX graph returned by `provlog_to_digraph`.
  - [x] Check generic properties Shofiya and Sam finished this.
    - [x] The file descriptor used in CloseOp is one returned by a prior OpenOp (or a special file descriptor).
    - [x] Verify we aren't "missing" an Epoch ID, e.g., 0, 1, 3, 4 is missing 2.
    - [x] Verify that the TID returned by CloneOp is the same as the TID in the InitOp of the new thread.
    - [x] Verify that the TID returned by WaitOp is a TID previously returned by CloneOp.
    - [x] Verify the graph is acyclic and has one root.
    - [x] Put some of these checks in a function, and have that function be called by `PROBE analysis --check`.
    - Note that the application may not close every file descriptor it opens; that would be considered a "sloppy" application, but it should still work in PROBE.
  - [x] Write a pthreads application for testing purposes (Saleha finished this).
  - [x] Verify some properties of the pthreads application.
    - [x] Verify that the main thread has N CloneOp followed by N WaitOps.
  - [x] Verify some properties of `cp a b`.
    - [x] Verify that `a` gets opened for reading.
    - [x] Verify that `b` gets opened for writing.
    - [x] Verify the file descriptors get closed at some point after both opens.
  - [x] Verify some properties of `sh -c "cat a ; cat b"`
    - [x] Verify that the root process has a CloneOp, WaitOp, CloneOp, WaitOp.
    - [x] Verify that the first child process has ExecOp, OpenOp (path should be `a`), and CloseOp. Analogously check the second child process.
  - [x] Verify that this doesn't crash `sh -c "sh -c 'cat a ; cat b' ; sh -c 'cat d ; cat e'"` (in the past it did)
  - [x] Continue along these lines one or two more cases.

- [ ] Set up CI
  - [x] Write [Justfiles](https://github.com/casey/just). Each of the following should be a target:
    - [x] Format Nix code with alejandra.
    - [x] Format Python code with Black (please add to `flake.nix`).
    - [x] Check Python code with Ruff (please add to `flake.nix`).
    - [x] Check Python code with Mypy.
    - [x] Run tests on the current machine.
  - [x] Write a CI script that uses Nix to install dependencies and run the Justfiles.
  - [x] Check (not format) code in Alejandra and Black.
  - [x] Figure out why tests don't work.
  - [ ] Run tests in an Ubuntu Docker container.
  - [ ] Run tests in a really old Ubuntu Docker container.
  - [ ] Figure out how to intelligently combine Nix checks, Just checks, and GitHub CI checks, so we aren't duplicating checks.
- [x] Write microbenchmarking
  - [x] Run performance test-cases in two steps: one with just libprobe record and one with just transcription. (3 new CLI entrypoints, described in comments in CLI.py)
  - [ ] Write interesting performance tests, using `benchmark/workloads.py` as inspiration.

Downstream applications:
- [ ] SSH wrapper
  - [ ] There should be a shell script named `ssh` that calls `./PROBE ssh <args...>`.
  - [ ] `./PROBE ssh <args...>` will determine which arguments are arguments to SSH and which are arguments to a command, if any. Note that `ssh` can be called with or without a command, e.g., `ssh user@remote command --args` or `ssh user@remote` (user types interactively). In the latter case, we should pretend the command was `$SHELL` in the remote environment, defaulting to bash.
  - [ ] `./PROBE ssh` will then determine the architecture and OS of the remote system. If the architecture and OS does not match the local, we should raise `NotImplementedError` explaining as much.
  - [ ] `./PROBE ssh` should install `libprobe.so` or `libprobe-dbg.so` (depending on a command-line flag), if absent, to the remote at `${XDG_DATA_HOME}`, defaulting to `$HOME/.local/share` if `XDG_DATA_HOME` is unset.
  - [ ] `./PROBE ssh` should create an empty directory on the remote.
  - [ ] `./PROBE ssh` should run `env LD_LIBRARY_PATH=path/to/libprobe.so PROBE_DIR=path/to/blank-dir <command> <args...>` (from earlier) on the remote.
  - [ ] `./PROBE ssh` should tar, gzip, and download the PROBE log directory to the local host for further processing. Assumme for the moment that `tar` and `gzip` exist on the remote. When the Rust wrapper is complete, we can eliminate this dependency.
  - Think about avoiding multiple SSH sessions, and think about assumptions on the remote host.

- [ ] Write an [SCP wrapper](https://www.wikiwand.com/en/Secure_copy_protocol). The wrapper should be a shell named `scp` that calls `./PROBE scp <args...>`. `./PROBE scp <args...>` should determine whether we are going remote->local or local->remote. It should look for provenance of the inodes of the target files on the "source" node (could be local or remote) in `${XDG_DATA_HOME:$HOME/.local/share}`. It should copy the releveant provenance tree of just those inodes to the "destination node" (either local or remote). Then it should call the "real" `scp` with the appropriate arguments.

- [ ] Write an [Rsync wrapper](https://rsync.samba.org/), which does the same thing as the SCP wrapper. Use `--dry-run` to determine which files will be accessed.

- [ ] From the NetworkX digraph, export (Shofiya is working on this):
  - [x] A dataflow graph, showing only files, processes, and the flow of information between them. The following rules define when there is an edge:
    1. Data flows from a file to a process if on any thread there is an OpenOp with the flags set to `O_RDWR` or `O_RDONLY`.
    2. Data flows from a process to a process if one process CloneOp's the other.
    3. Data flows from a process to a file if on any thread there is a OpenOp with the flags set to `O_RDWR` or `O_WRONLY`.
  - [ ] Capture the command of the process in libprobe. Currently, the `cmd` property of the `ProcessNode` in the dataflow graph is assigned a value using a map that associates each `process_id` with the corresponding command. This map is generated by a stop-gap function that constructs a command string using the `program-name` from `InitExecEpochOp` and the `file` from `OpenOp`. However, this function often fails to generate the correct command for certain operations. For instance, it struggles with cases such as `cat a.txt; cat a.txt` and the execution of compiled C programs like `./compiled_c_file`.
  - [ ] [Process Run Crate](https://www.researchobject.org/workflow-run-crate/profiles/process_run_crate/) (Saleha is working on this)
  - [ ] [Common Workflow Language](https://www.commonwl.org/)
    - [ ] Write a test that runs the resulting CWL.
  - [ ] Nextflow (Kyrilos is working on this)
    - [ ] Write a test that runs the resulting CWL.
  - [ ] Makefile
    - [ ] Write a test that runs the resulting Makefile.
  - [ ] LLM context prompt (Kyrilos is working on this)
    - Build on the work of Nichole Bufford et al.

- [ ] Statically link libprobe. It should have no undefined symbols.

Design issues:
- [ ] Consider how to combine provenance from multiple sources
  - [ ] Consider language-level sources like rdtlite
  - [x] Consider combining across multiple runs of PROBE
  - [x] Consider combining across multiple hosts

- [ ] Think about in situ transcription and analysis
  - Think about assumptions in analysis
  - Think about front-end and UI/UX

Performance issues:
- [ ] Have better benchmarks

- [ ] InodeTable should be shared across process-trees or perhaps globally

- [ ] Unify the data and op Arenas
  - [ ] Test high mem
  - [ ] Put magic bytes in arena


- [ ] Use lock-free implementation of InodeTable

Documentation:
- [ ] Make the CLI better. You shouldn't need to give `-f` to make repeated applications work. You shouldn't need to give `--input`.

- [ ] Document CLI tool.

- [ ] Combine Python and Rust CLIs.

- [ ] Improve the README.

- [ ] Style output with Rich.

- [ ] Style output of Rust tool.

- [ ] Package for the following platforms:
  - [ ] It should be obvious how to build libprobe and probe cli (Rust) with Nix from the README.
  - [ ] The repository should be an installable Python package, using the PEP 518 (pyproject.toml). Consider having one Python package with bundled binaries and one without.
  - [ ] PyPI
  - [ ] Nix
  - [ ] Spack
  - [ ] Guix
  - [ ] Docker image (consider whether to publish DockerHub, Quay, GHCR, or somewhere else).
  - [ ] Statically linked, downloadable binary
    - Built in CI on each "release" and downloadable from GitHub.

- [ ] Changelog

- [ ] Explain design decisions

Nice to have:
- [ ] Make it easier to get to the debug build of probe cli.
  - Build both versions, called `probe` and `probe_dbg`.
  - `probe_dbg` should use `libprobe_dbg`
  - Get rid of `--debug`

- [ ] Add more syscalls
  - [ ] Add Dup ops and debug `bash -c 'head foo > bar'` (branch add-new-ops). Sam is working on this

- [ ] Add more Ops (see branch add-new-ops)

- [ ] Libprobe should identify which was the "root" process.

- [ ] Sort readdir order in record and replay phases.

- [ ] Write a FUSE that maps inodes (underlying fs) to inodes (of our choosing). Write an option for replay to use this FUSE.

- [ ] Link with libbacktrace on `--debug` runs.

- [ ] Refactor some identifiers in codebase.
  - [ ] prov_log_process_tree -> process_tree
  - [ ] (pid, ex_id, tid, op_id) -> dataclass
  - [ ] digraph, process_graph -> hb_graph
  - [ ] Reformat Nix and Python
  - [ ] Use Clang's non-null attribute.

  [ ] Reformat repository layout
    - [ ] `probe_src/python` -> `python-wrapper` or just `/` (moving children up a level
    - [ ] `frontend` -> `rust-frontend`, and renaming the packages in it to `cli`, `macros`, and `pygen`
    - [ ] `reproducibility_tests` -> `tests`
    - [ ] Move tests to root level?
    - [ ] Distinguish between unit-tests and end-to-end tests
    - [ ] Ensure Arena tests, struct_parser tests, and c tests are being compiled and exercised. Currently, I don't think the c tests are being compiled. Should pytest runner compile them or Justfile? Clang-tidy should cover them.

Research tasks:
- [ ] Develop user study
  - [ ] Develop protocol for assessing ease-of-use.
  - [ ] Apply for IRB.
  - [ ] Do user study.

- [ ] Submit publication
  - [ ] Have a compelling benchmark
  - [ ] Describe the theory of PROBE (how does it work? what are the limitations?)
  - [ ] Describe the operation of PROBE
  - [ ] Describe the user-study
