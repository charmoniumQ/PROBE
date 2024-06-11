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

4. Run PROBE with `./PROBE --make head ../flake.nix`

  - Note that `--make` will cause libprobe to be re-compiled or compiled, so if you make changes to libprobe or you haven't compiled it before, use this flag.

  - This will output `probe_log` unless you pass `--output <desired_output_path>`.

  - Also note `--debug` which runs a build of libprobe that is more verbose, has runtime checks, and has debug symbols.
  
  - Also note `--gdb` which loads libprobe, your command, and drops you into a GDB shell.

5. Try `./PROBE dump`, which will read `probe_log` unless you pass `--input <desired_input_path>`. This should show a series of provenance operations, e.g.,
  
   ```
   InitExecEpochOp(process_id=116448, exec_epoch=0, process_birth_time=timespec(tv_sec=1718127174, tv_nsec=333602925), program_name='head')
   InitThreadOp(process_id=116448, process_birth_time=timespec(tv_sec=1718127174, tv_nsec=333602925), exec_epoch=0, sams_thread_id=0)
   OpenOp(path=Path(dirfd_minus_at_fdcwd=0, path='../flake.nix', device_major=0, device_minor=32, inode=123261484, stat_valid=True, dirfd_valid=True), flags=0, mode=0, fd=6, ferrno=0)
   CloseOp(low_fd=6, high_fd=6, ferrno=0)
   CloseOp(low_fd=1, high_fd=1, ferrno=0)
   CloseOp(low_fd=2, high_fd=2, ferrno=0)
   ```

## FAQ

- Why doesn't your flake define a Nix app or Nix package?
  - Because I have a finite amount of time, and I'm still in the unstable development phase.

## Prior art

- [RR-debugger](https://github.com/rr-debugger/rr) which is much slower, but features more complete capturing, lets you replay but doesn't let you do any other analysis.

- [Sciunits](https://github.com/depaul-dice/sciunit) which is much slower, more likely to crash, has less complete capturing, lets you replay but doesn't let you do other analysis.

- [Reprozip](https://www.reprozip.org/) which is much slower and has less complete capturing.

- [CARE](https://proot-me.github.io/care/) which is much slower, has less complete capturing, and lets you do containerized replay but not unpriveleged native replay and not other analysis.

- [FSAtrace](https://github.com/jacereda/fsatrace) which is more likely to crash, has less complete capturing, and doesn't have replay or other analyses.
