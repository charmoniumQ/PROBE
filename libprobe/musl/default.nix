{musl}:
musl.overrideAttrs (prev: {
  patches =
    (prev.patches or [])
    ++ [
      ./no-main.patch
    ];

  postInstall = ''
    ${prev.postInstall or ""}

    strip -N dladdr -N dladdr1 -N dlclose -N dldump -N dlerror -N dlinfo -N dlmopen -N dlopen -N dlsym $out/lib/libc.a
  '';
})
