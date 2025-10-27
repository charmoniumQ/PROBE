# Setting new papers

So far, papers are coming from the last lines of `test.txt`, in order. Look for `$repo_url`.

Create entry in `repos.yaml`.

Follow the other entries there for guidance.

I've tried reduce the number of epochs/iterations/resolution as much as possible (Note where the reductions took place).

# To run a paper that I've already set up

Run `nix develop` shell in the project-root (`../..`).

``` sh
python run_datasets.py neurve [--run]
# this creates an image for the neurve entry of `repos.yaml`, `nerve:0.0.x`, where `x` is defined by the PROBE version specified by script or by commandline (`--probe-tag 0.0.x`).
# It prints the command-to-run, but you can also give `--run` to just run the default run command.

#From this container created above, we should be able to do
probe record -f ./run.sh

```

# Goals
- `probe record` not crash.
- `probe py export dataflow-graph --loose` go without crashing.
- [`probe py export dataflow-graph --strict` go without crashing.]
- Calculate the performance impact.
- Create heuristics to classify files into the following categories, based on the position in the graph AND on examining file:
  - datasets, code, weights, training script, testing script, data acquisition scripts, plotting scripts
  - For example, if we see an exec, we can know that the thing being execed is an executable, and if it is named Python, then the first non-flag argument is a Python script. (uses only fact from the graph)
  - Could run `file` on the files to get more heuristics.
  - Might involve tagging those classes by hand for the known papers, comparing with what automated heurstics would say.
  
