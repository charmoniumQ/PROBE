There are two relevant glibc versions:

1. The version that we compile against, "compile-time version"

2. The set-of-versions that PROBE can run with, "runtime version"

PROBE uses the system's libc in three ways:

1. PROBE dynamically library-loads (`dlopen()`/`dlsym()`) and interposes symbols relevant to I/O. This does **not constrain the version** of libc much at all. We will work with whatever libc we have. If a function is not present, we simply won't interpose it.

2. PROBE statically uses some function, struct, and constant definitions in glibc's headers, **constraining compile-time version of glibc**.

   - `generated/libc_hooks.c` currently assumes _someone else_ defines the relevant functions that we want to override, the structs used as arguments to those functions, and the constants that are used as flags to those functions. We would just need to copy/hardcode/backport those definitions from the current compile-time version Glibc into libprobe.

3. PROBE dynamically links against glibc functions in order to do it's PROBE thing (e.g., `printf(...)`), **constraining the run-time version of glibc**

   - When we call `printf(...)`, the linker puts a dependency on `printf@GLIBC_2.3.4`, where 2.3.4 was the most recent version that the behavior of `printf` changed in a backwards incompatible way. Glibc maintains "backwards compatibility", so any environment with a glibc _newer_ than 2.3.4 should be able to run a program with a dependency on `printf@GLIBC_2.3.4`.

   - We can reduce the dependency by avoiding to use glibc (Jenna's work), and building against an old version of glibc.

   - Run `nm --dynamic libprobe/.build/libprobe.so` to find such requirements. 

**How I decided to use Glibc=2.33 at compile-time:** When compiling against the latest version of Glibc, the newest symbol needed was `pthread_something_or_other` at 2.34. So I set the version to the latest version right before that, 2.33. Now the newest needed symbol is `memcpy@GLIBC_2.14`. 2.14 is older than the [oldest Glibc in Nixpkgs](https://lazamar.co.uk/nix-versions/?channel=nixos-unstable&package=glibc), 2.18.

But when I actually tried that, PROBE still links against pthreads.

make: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.32' not found (required by /nix/store/q29bwjibv9gi9n86203s38n0577w09sx-glibc-2.33-117/lib/libpthread.so.0)

**Which OS does this cover?**: Most released after 2012, including Ubuntu 12.04 Precise, Debian 8 Jessie, CentOS/RHEL 7.

| Linux distro       | Distro version    | Release date | Glibc version | PROBE works? |
|--------------------|-------------------|--------------|---------------|--------------|
| Ubuntu             | 12.04 LTS Precise | 2012-04      | 2.15          | Y            |
| Ubuntu             | 10.04 LTS Lucid   | 2010-04      | 2.11          | N            |
| Debian             | 8 Jessie          | 2015-04      | 2.19          | Y            |
| Debian             | 7 Wheezy          | 2013-05      | 2.13          | N            |
| CentOS (c.f. RHEL) | 7.x               | 2014-07      | 2.17          | Y            |
| CentOS (c.f. RHEL) | 6.x               | 2011-11      | 2.12          | N            |

Run `podman run --rm ubuntu:12.04 ldd --version` to quick check.

## Problems

When we don't link with `-lpthread`, we are unable to resolve `pthread_getspecific`. I don't think that can easily be implemented without support from the client's pthread library; I am unsure of the performance implications of using `dlsym("pthread_getspecific")` vs having the symbol resolved by the dynamic linker (is there an extra indirection per-call in the former?). So I added `-lpthread`.

However, this is not enough. When I run PROBE (modern or old system!), I get

```bash
$ probe record -f ls
ls: symbol lookup error: /nix/store/bqbg6hb2jsl3kvf6jgmgfdqy06fpjrrn-glibc-2.30/lib/libpthread.so.0: undefined symbol: __nanosleep_nocancel, version GLIBC_PRIVATE
[2025-10-20T02:46:51Z WARN  probe::record] Recorded process exited with code 127
```

I believe this is because we are using _old_ libpthreads and _new_ glibc. When I use `LD_DEBUG=all`, notice how `libpthread` from `glibc-2.32` is requesting `__libc_siglongjmp` which presumably exists in 2.32, but is only looked up in 2.40. Presumably we need to use _new_ libpthreads and _new_ glibc. This goes against the design principles of Nix, as we want libpthreads from the environment rather than from the Nix store.

```
$ LD_DEBUG=all probe record -f ls
<snip>
   1228932:     symbol=__libc_siglongjmp;  lookup in file=/home/sam/box/PROBE/cli-wrapper/target/debug/probe [0]
   1228932:     symbol=__libc_siglongjmp;  lookup in file=/home/sam/box/PROBE/libprobe/.build/libprobe.so [0]
   1228932:     symbol=__libc_siglongjmp;  lookup in file=/nix/store/xp989kyfg52803fmkzbz5py35jphcpgd-gcc-14.3.0-lib/lib/libgcc_s.so.1 [0]
   1228932:     symbol=__libc_siglongjmp;  lookup in file=/nix/store/qhw0sp183mqd04x5jp75981kwya64npv-glibc-2.40-66/lib/libc.so.6 [0]
   1228932:     symbol=__libc_siglongjmp;  lookup in file=/nix/store/qhw0sp183mqd04x5jp75981kwya64npv-glibc-2.40-66/lib/ld-linux-x86-64.so.2 [0]
   1228932:     symbol=__libc_siglongjmp;  lookup in file=/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/libpthread.so.0 [0]
   1228932:     /nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/libpthread.so.0: error: symbol lookup error: undefined symbol: __libc_siglongjmp, version GLIBC_PRIVATE (fatal)
/home/sam/box/PROBE/cli-wrapper/target/debug/probe: symbol lookup error: /nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/libpthread.so.0: undefined symbol: __libc_siglongjmp, version GLIBC_PRIVATE
[2025-10-20T02:49:41Z WARN  probe::record] Recorded process exited with code 127
```

Somehow, the `ldd` is reporting old glibc and old libpthread, but when we actually run it with `LD_DEBUG=all`, we see new glibc and old libpthread:

```
$ ldd libprobe/.build/libprobe.dbg.so 
        linux-vdso.so.1 (0x00007f3cfffa9000)
        libpthread.so.0 => /nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/libpthread.so.0 (0x00007f3cfff5a000)
        libc.so.6 => /nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/libc.so.6 (0x00007f3cffd99000)
        /nix/store/lmn7lwydprqibdkghw7wgcn21yhllz13-glibc-2.40-66/lib64/ld-linux-x86-64.so.2 (0x00007f3cfffab000)
```

If this fixes it, revert the `pthreads` backporting done in `inode_table.c`, `probe_libc.c`, `probe_libc.h`, and `check_needed_syms.py` in the most recent commit.

It appears that the `RUNPATH` of `probe` binary is influencing the lookup of symbols in `LD_PRELOAD=... child`.

```
     24556:     file=libpthread.so.0 [0];  needed by /home/sam/box/PROBE/libprobe/.build/libprobe.so [0]
     24556:     find library=libpthread.so.0 [0]; searching
     24556:      search path=/etc/sane-libs:/nix/store/b5a6rpl9ywibgydq22pzvrrkgqd5irzs-pipewire-1.4.6-jack/lib         (LD_LIBRARY_PATH)
     24556:       trying file=/etc/sane-libs/libpthread.so.0
     24556:       trying file=/nix/store/b5a6rpl9ywibgydq22pzvrrkgqd5irzs-pipewire-1.4.6-jack/lib/libpthread.so.0
     24556:      search path=/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/glibc-hwcaps/x86-64-v4:/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/glibc-hwcaps/x86-64-v3:/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/glibc-hwcaps/x86-64-v2:/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib:/nix/store/xp989kyfg52803fmkzbz5py35jphcpgd-gcc-14.3.0-lib/lib:/nix/store/8b9srwwmrwmh1yl613cwwj7gydl87br6-gcc-14.3.0-libgcc/lib/glibc-hwcaps/x86-64-v4:/nix/store/8b9srwwmrwmh1yl613cwwj7gydl87br6-gcc-14.3.0-libgcc/lib/glibc-hwcaps/x86-64-v3:/nix/store/8b9srwwmrwmh1yl613cwwj7gydl87br6-gcc-14.3.0-libgcc/lib/glibc-hwcaps/x86-64-v2:/nix/store/8b9srwwmrwmh1yl613cwwj7gydl87br6-gcc-14.3.0-libgcc/lib           (RUNPATH from file /home/sam/box/PROBE/cli-wrapper/target/debug/probe)     24556:       trying file=/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/glibc-hwcaps/x86-64-v4/libpthread.so.0
     24556:       trying file=/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/glibc-hwcaps/x86-64-v3/libpthread.so.0
     24556:       trying file=/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/glibc-hwcaps/x86-64-v2/libpthread.so.0
     24556:       trying file=/nix/store/9l06v7fc38c1x3r2iydl15ksgz0ysb82-glibc-2.32/lib/libpthread.so.0
```
