import xdg_base_dirs
import pathlib
import typing


SYSTEMD_MACHINE_ID = pathlib.Path("/etc/machine-id")


# PROBE application key
# Application name + unique (random) string
APPLICATION_KEY = b"PROBE \xe5\x06PKsQz\xa3yq5\x82\x14\xd2\x85\x90"


# Unlike xdg_cache_dir, xdg_state_home is less likely to be shared.
# Unlike xdg_runtime_dir, xdg_state_home is allowed to persist across sessions
# Random string makes sure this is unique, in the unlikely event there is another application called PROBE
ALTERNATIVE_MACHINE_ID = pathlib.Path(xdg_base_dirs.xdg_state_home()).resolve() / "PROBE-f26a6f0c" / "machine-id"


# echo -e '#include <fcntl.h>\nAT_FDCWD' | gcc -E - | tail --lines=1
AT_FDCWD: typing.Final = -100

# echo -e '#define _GNU_SOURCE\n#include <fcntl.h>\nAT_EMPTY_PATH' | gcc -E - | tail --lines=1
AT_EMPTY_PATH: typing.Final = 4096
