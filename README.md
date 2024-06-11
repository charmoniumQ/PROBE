# PROBE: Provenance for Replay OBservation Engine

This program executes and monitors another program, recording its inputs and outputs using `$LD_PRELOAD`.

These inputs and outputs can be joined in a provenance graph.

The provenance graph tells us where a particular file came from.

## Running

1. Install Nix with flakes.

  - If you don't already have Nix, use the [Determinate Systems installer](https://install.determinate.systems/).

  - If you already have Nix (but not NixOS), enable flakes by adding the following line to `~/.config/nix/nix.conf` or `/etc/nix/nix.conf`:

    ```
    experimental-features = nix-command flakes
    ```
  - If you already have Nix and are running NixOS, enable flakes with by adding `nix.settings.experimental-features = [ "nix-command" "flakes" ];` to your configuration.

2. Run `nix develop` to enter the development environment.

3. `cd probe_src`

4. Run PROBE with `./PROBE --make -- ls`

  - Note that `--make` will cause libprobe to be re-compiled or compiled, so if you make changes to libprobe or you haven't compiled it before, use this flag.

5. Try `./PROBE process-graph`.
