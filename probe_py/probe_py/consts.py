import typing
import xdg_base_dirs


PROBE_HOME: typing.Final = xdg_base_dirs.xdg_data_home() / "PROBE"

# echo -e '#include <fcntl.h>\nAT_FDCWD' | gcc -E - | tail --lines=1
AT_FDCWD: typing.Final = -100

# echo -e '#define _GNU_SOURCE\n#include <fcntl.h>\nAT_EMPTY_PATH' | gcc -E - | tail --lines=1
AT_EMPTY_PATH: typing.Final = 4096
