def _activate():
    $SPACK_ENV = "/home/sam/.local/share/spack/var/spack/environments/test"

    def deactivate():
        del $SPACK_ENV
        $ACLOCAL_PATH.pop(0)
        # $CMAKE_PREFIX_PATH.pop(0)
        $MANPATH.pop(0)
        $MANPATH.pop(0)
        $PATH.pop(0)
        $PKG_CONFIG_PATH.pop(0)
        $PKG_CONFIG_PATH.pop(0)
        $PKG_CONFIG_PATH.pop(0)

    aliases["despacktivate"] = deactivate

    from xonsh.tools import EnvPath

    if "ACLOCAL_PATH" not in ${...}:
        $ACLOCAL_PATH = EnvPath()
    $ACLOCAL_PATH.insert(0, "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view/share/aclocal")

    # CMAKE_PREFIX_PATH uses ; as the delimiter so we can't use EnvPath
    #if "CMAKE_PREFIX_PATH" in ${...}:
    #    $CMAKE_PREFIX_PATH = ";" + $CMAKE_PREFIX_PATH
    #$CMAKE_PREFIX_PATH = "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view" + ${...}.get("CMAKE_PREFIX_PATH", "")

    if "MANPATH" not in ${...}:
        $MANPATH = EnvPath()
    $MANPATH.insert(0, "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view/man")
    $MANPATH.insert(0, "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view/share/man")

    $PATH.insert(0, "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view/bin")

    if "PKG_CONFIG_PATH" not in ${...}:
        $PKG_CONFIG_PATH = EnvPath()
    $PKG_CONFIG_PATH.insert(0, "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view/lib/pkgconfig")
    $PKG_CONFIG_PATH.insert(0, "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view/lib64/pkgconfig")
    $PKG_CONFIG_PATH.insert(0, "/home/sam/.local/share/spack/var/spack/environments/test/.spack-env/view/share/pkgconfig")

_activate()
del _activate
