# Provenance in DAWs for reproducibility, parallelism, and comprehensibility

The world isn't always perfectly structured. One often has to deal with data analysis 'workflows' (DAWs) that aren't written in a structured workflow language, resembling more a 'pile of scripts', whose dependencies are implicit and unknown. I will present [**PROBE**][1], a provenance-tracing tool; as the user executes ad hoc commands, PROBE will record each file and process invoked. Armed with such a provenance trace, one can visualize the underlying dataflow, identify actually-used dependencies, create a container image, and convert to a workflow automatically.

[1]: https://github.com/charmoniumQ/PROBE
