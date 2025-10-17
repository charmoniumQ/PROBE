There are two relevant glibc versions:

1. The version that we compile against, "compile-time version"

2. The set-of-versions that PROBE can run with, "runtime version"

PROBE uses the system's libc in two ways:

1. PROBE dynamically library-loads (`dlopen()`/`dlsym()`) and interposes symbols relevant to I/O. This does **not constrain the version** of libc much at all. We will work with whatever libc we have. If a function is not present, we simply won't interpose it.

2. PROBE statically uses some function, struct, and constant definitions in glibc's headers, **constraining compile-time version of glibc**.

   - `generated/libc_hooks.c` currently assumes _someone else_ defines the relevant functions that we want to override, the structs used as arguments to those functions, and the constants that are used as flags to those functions. We would just need to copy/hardcode/backport those definitions from the current compile-time version Glibc into libprobe.

2. PROBE dynamically links against glibc functions in order to do it's PROBE thing (e.g., `printf(...)`), **constraining the run-time version of glibc**

   - When we call `printf(...)`, the linker puts a dependency on `printf@GLIBC_2.3.4`, where 2.3.4 was the most recent version that the behavior of `printf` changed in a backwards incompatible way. Glibc maintains "backwards compatibility", so any environment with a glibc _newer_ than 2.3.4 should be able to run a program with a dependency on `printf@GLIBC_2.3.4`.

   - We can reduce the dependency by avoiding to use glibc (Jenna's work), and building against an old version of glibc.

   - Run `nm --dynamic libprobe/.build/libprobe.so` to find such requirements. 

**How I decided to use Glibc=2.33 at compile-time:** When compiling against the latest version of Glibc, the newest symbol needed was `pthread_something_or_other` at 2.34. So I set the version to the latest version right before that, 2.33. Now the newest needed symbol is `memcpy@GLIBC_2.14`. 2.14 is older than the [oldest Glibc in Nixpkgs](https://lazamar.co.uk/nix-versions/?channel=nixos-unstable&package=glibc), 2.18.


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
