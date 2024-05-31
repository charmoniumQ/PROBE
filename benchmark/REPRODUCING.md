# Reproducing

We split this into three steps:

1. Getting the software environment.
2. Running the benchmarks.
3. Running the analysis.


## Getting the software environment with Nix

Nix package manager^[See <https://nixos.org/guides/how-nix-works>] is a user-level package manager available on many platforms.
Nix uses build-from-source and a binary cache; this is more resilient than Dockerhub because if the binary cache goes down or removes packages for any reason, the client can always build them from source, so long as the projects don't disappear from GitHub.
We considered creating a Docker image, but BenchExec, the tool we use to get consistent running times, manipulates cgroups and systemd, and we did not have enough time to figure out how to run in Docker or Podman.

Install Nix with:

```sh
$ curl -f -L https://install.determinate.systems/nix | sh -s -- install
```

This installer also enables "flakes" and the "nix-command".
If you installed Nix by another method, see [this page](https://nixos.wiki/wiki/Flakes) to enable flakes and the nix-command.

```sh
$ git clone https://github.com/charmoniumQ/prov-tracer
$ cd prov-tracer/benchmark
```

Use Nix to build.
We used `--max-jobs` to enable parallelism.
This step takes about half an hour on a modest machine with residential internet.

```sh
$ nix build --print-build-logs --max-jobs $(nproc) '.#env'
```

### Extra steps

- One needs Kaggle credentials to run the data science notebooks. Log in to Kaggle, go to Profile, go to Account, generated an API key called "kaggle.json", download it, move it to `​~/.kaggle/kaggle.json`, `chmod 600 ~/.kaggle/kaggle.json`. Run `nix shell '.#kaggle' --command kaggle --help` and verify there are no errors.

- Follow directions in [Benchexec](https://github.com/sosy-lab/benchexec/blob/main/doc/INSTALL.md) to enable cgroups. Run `result/bin/python -m benchexec.check_cgroups` and verify there are no errors.

- Test `nix shell '.#rr' --command rr record result/bin/ls`. If this issues an error regarding `kernel.perf_event_paranoid`, follow its advice and confirm that resolves the error.

  - AMD Zen CPUs may require [extra setup](https://github.com/rr-debugger/rr/wiki/Zen)

  - Note that RR may require [extra setup](https://github.com/rr-debugger/rr/wiki/Will-rr-work-on-my-system) for virtual machines.
  
  - Finally, AMD CPUs are hit-or-miss with rr, due to its low-level machine-code operations. This is a known weakness of `rr`. If you can't get `rr` to work, and you can't get an Intel CPU, you may disable `rr` by removing it from `working` at the bottom of `prov_collectors.py`. You will still be able to collect statistics on the other (more portable) provenance collectors.

## Running the benchmarks

Note that we use the Python from our software environment, not from the system, to improve determinism.
We wrote a front-end to run the scripts called `runner.py`.


Run with `--help` for more information.
Briefly, it takes a `--collectors`, `--workloads`, `--iterations`, and `--parallelism` arguments, which specify what to run.
For the paper, we ran

```sh
$ ./result/bin/python runner.py \
    --collectors working \
    --workloads working \
    --iterations 3 \
    --parallelism 1
```

Multiple `--collectors` and `--workloads` can be given, for example,

```sh
$ ./result/bin/python runner.py \
    --collectors noprov \
    --collectors strace \
    --workloads lmbench \
    --workloads postmark
```

See the bottom of `prov_collectors.py` and `workloads.py` for the name-mapping.

## Running the analysis

The analysis is written in a Jupyter notebook called ``notebooks/cross-val.ipynb''.
It begins by checking for anomalies in the data, which we've automated as much as possible, but please sanity check the graphs before proceeding.

The notebook can be launched from our software environment by:

```sh
env - result/bin/jupyter notebook
```

## Adding new benchmark items or provenance collectors

For new benchmark items,

1. Go to `workload.py`.
2. Write a new workload class that implements the `Workload` interface.
3. Add an instance of your workload class to `WORKLOAD_GROUPS`.
4. Call `./result/bin/runner` (see above) with `--workloads workload_name` where `workload_name` is the lowercased name of your workload class or name of a group containing your workload class.

For new provenance collectors:

1. Go to `collectors.py`.
2. Write a new class that implements the `Collector` interface.
3. Add an instance of your workload class to `COLLECTORS`.
4. Call `./result/bin/runner` (see above) with `--collectors collector_name` where `collector_name` is the lowercased name of your collector class or name of a group containing your collector class.


Note that the attribute `nix_packages`, in both cases, contains a list of strings that reference packages defined as in package outputs for the current architecture the `flake.nix`.
Using Nix to build our software environment ensures that all architectures and POSIX platforms can reproducibly build the relevant software environments.
