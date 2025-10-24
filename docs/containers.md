# Running PROBE in containers

## Injecting PROBE at run-time

This method injects PROBE into an existing image at container-run-time (no need to rebuild image). Changes made on the host will propagate into the container.

Enter the devshell with `nix develop`.

Run `just compile`.

Add the following arguments to the `<FLAGS>` of `podman run <FLAGS> <IMG> [CMD]` or `docker run <FLAGS> <IMG> [CMD]`:

```
    --env PROBE_LIB=$PROBE_LIB \
    --env PROBE_PYTHONPATH=$PROB_PYTHONPATH \
    --env PROBE_PYTHON=$PROBE_PYTHON \
    --env probe=$(which probe) \
    --volume=$PWD:$PWD:ro \
    --volume=/nix/store:/nix/store:ro \
```

Once inside the container, run PROBE by `$probe record ...`. Make sure to single-quote `$probe` if you are passing it on the command-line. For example,

```
podman run \
    --rm \
    -it \
    ... flags from earlier \
    ubuntu:24.04 \
    bash -c '$probe record ls'
```

The build is updatable; As soon as you make changes on the host side and recompile (`just compile`), the changes will apply to `$probe` in the container.

## Injecting PROBE at build-time

In this method, we modify an existing `Containerfile` or `Dockerfile`, baking in PROBE. We will use the [multi-stage build](https://docs.docker.com/build/building/multi-stage/) pattern, so the target Containerfile will have two (or more) `FROM`s. The last one is the one that "counts", but the prior ones can be accessed with `COPY --from`. To the target `Containerfile`, prepend to the very top:

```
ARG PROBE_VER
FROM probe:${PROBE_VER} AS probe
```

And append to the very bottom:

```
COPY --frome=PROBE /nix/store /nix/store
COPY --frome=PROBE /bin/probe /bin/probe
```

See [`./Containerfile`](Containerfile)

Now, we will build a PROBE-only container image. This can be done through the Nix build-system natively rather than `docker build ...`. Increment `probe-ver` in `flake.nix`, to give the container have a unique tag.

```
podman load --input $(nix build --print-out-paths --no-link '.#docker-image')
```

Now we can build the target Containerfile with, `probe build --build-arg PROBE_VERSION=0.0.13` (replacing 0.0.13 with whatever version was used earlier).

## Building PROBE in a container

If you can't install Nix on the host but do have Docker or Podman, you can build PROBE in a container with:

```
FROM <any Linux image>

RUN <install curl>

ENV PATH="${PATH}:/nix/var/nix/profiles/default/bin" \
    USER=root
RUN curl -fsSL https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "sandbox = false" --init none --no-confirm && \
    ... Contine with installation instructions from ../README.md
```
