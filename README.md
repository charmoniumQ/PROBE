# PROBE: Provenance for Replay OBservation Engine

This program executes and monitors another program, recording its inputs and outputs using `$LD_PRELOAD`.

These inputs and outputs can be joined in a provenance graph.

The provenance graph tells us where a particular file came from.

The provenance graph can help us re-execute the program, containerize the program, turn it into a workflow, or tell us which version of the data did this program use.

## Installing PROBE

1. Install Nix with flakes. This can be done on any Linux (including Ubuntu, RedHat, Arch Linux, not just NixOS), MacOS X, or even Windows Subsystem for Linux. See [Determinate Nix Installer documentation](https://github.com/DeterminateSystems/nix-installer/blob/main/README.md) for more details.

   ```bash
   curl -fsSL https://install.determinate.systems/nix | sh -s -- install

   # In container,
   #curl -fsSL https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "sandbox = false" --init none --no-confirm
   ```
   
2. Re-log-in or activate Nix in the current shell.

   ```bash
   export PATH="${PATH}:/nix/var/nix/profiles/default/bin"
   ```

3. Optionally, use our public binary cache to speed up the installation.

   ```bash
   nix profile install --accept-flake-config nixpkgs#cachix
   cachix use charmonium
   ```

4. Install PROBE or run PROBE without permanently installing. In the latter case, the

   ```bash
   nix profile install github:charmoniumQ/PROBE
   probe --help
   
   # Or run without installing.
   # Nix will install PROBE into a virtual environment that is only activated in the current shell.
   #nix run github:charmoniumQ/PROBE -- [probe args go here]

   # Use `nix store gc` to reclaim disk space consumed by the previous command's virtual environment.
   ```

5. Now you should be able to run `probe record [-f] [-o probe_log] <cmd...>`. `-f` is needed to overwrite a pre-existing `probe_log`.

  ```bash
  probe record ./script.py --foo bar.txt
  probe export debug-text
  ```

TODO: tidy up this

To run PROBE in a docker image,

``` bash
docker load --input $(nix build --print-out-paths --no-link .#docker-image)
```

Emits a container called: `probe:0.0.x`, where `x` is replaced with an integer.

This can be run directly, with `docker run --rm -it probe:0.0.x /bin/sh`

Or PROBE can be `COPY`ed into other Docker images with

``` bash
FROM probe:0.0.x AS probe

FROM real_base_image

...

COPY --from=probe /nix /nix
COPY --from=probe /bin/probe /bin/probe
```

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

Any flag after the first positional argument is treated as an argument to the command, not `probe`.

This creates a file called `probe_log`. If you already have that file from a previous recording, give `probe record -f` to overwrite.

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

Try exporting to different formats.


``` bash
probe export --help
```

## Developing PROBE

1. Follow the previous step to install Nix.

2. Acquire the source code: `git clone https://github.com/charmoniumQ/PROBE && cd PROBE`

3. Run `nix develop`. This will leave you in a _Nix development shell_, with all the development tools you need to develop and build PROBE. It is like a virtualenv, in that it is isolated from your system's pre-existing tools. In the development shell, we all have the same version of Python with all the same packages. You can exit it by dyping `exit`.

4. From _within the development shell_, type `just compile`. This compiles the Rust, C, and generated-Python components. If you hack on either, run `just compile` again before continuing.

5. The manually-written Python scripts should already be added to the `$PYTHONPATH`. You should be able to edit them in place.

6. Run `probe <args...>` or `python -m probe_py.manual.cli <args...>` to invoke the Rust or Python code respectively.

7. **Before submitting a PR**, run `just pre-commit` which will run pre-commit checks.

## Directory structure

- `libprobe`: Library that implements interposition (C, Make, Python; happens to be manual and code-gen).
  - `libprobe/include`: Headers that will be used by the Rust wrapper to read PROBE data.
  - `libprobe/src`: Main C sources of `libprobe`.
  - `libprobe/generator`: Python and C-template code-generator.
  - `libprobe/generated`: (Generated, not committed to Git) output of code-generation.
  - `libprobe/Makefile`: Makefile that runs all of `libprobe`; run `just compile-cli` to invoke.
- `cli-wrapper`: (Cargo workspace) code that wraps libprobe.
  - `cli-wrapper/cli`: (Cargo crate) main CLI.
  - `cli-wrapper/lib`: (Cargo crate) supporting library functions.
  - `cli-wrapper/macros`: (Cargo crate) supporting macros; they use structs from `libprobe/include` to create Rust structs and Python dataclasses.
  - `cli-wrapper/frontend.nix`: Nix code that builds the Cargo workspace; Gets included in `flake.nix`.
- `probe_py`: Python Code that implements analysis of PROBE data (happens to be manual and code-gen), should be added to `$PYTHONPATH` by `nix develop`
  - `probe_py/probe_py`: Main package to be imported or run.
  - `probe_py/pyproject.toml`: Definition of main package and dependencies.
  - `probe_py/tests`: Python unittests, i.e., `from probe_py import foobar; test_foobar()`; Run `just test-py`.
  - `probe_py/mypy_stubs`: "Stub" files that tell Mypy how to check untyped library code. Should be added to `$MYPYPATH` by `nix develop`.
- `tests`: End-to-end opaque-box tests. They will be run with Pytest, but they will not test Python directly; they should always `subprocess.run(["probe", ...])`. Additionally, some tests have to be manually invoked.
- `docs`: Documentation and papers.
- `benchmark`: Programs and infrastructure for benchmarking.
  - `benchmark/REPRODUCING.md`: Read this first!
- `flake.nix`: Nix code that defines packages and the devshell.
- `setup_devshell.sh`: Helps instantiate Nix devshell.
- `Justfile`: "Shortcuts" for defining and running common commands (e.g., `just --list`).
