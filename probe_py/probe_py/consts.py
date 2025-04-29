import pathlib
import typing


SYSTEMD_MACHINE_ID = pathlib.Path("/etc/machine-id")


# PROBE application key
# Application name + unique (random) string
APPLICATION_KEY = b"PROBE \xe5\x06PKsQz\xa3yq5\x82\x14\xd2\x85\x90"


# echo -e '#include <fcntl.h>\nAT_FDCWD' | gcc -E - | tail --lines=1
AT_FDCWD: typing.Final = -100

# echo -e '#define _GNU_SOURCE\n#include <fcntl.h>\nAT_EMPTY_PATH' | gcc -E - | tail --lines=1
AT_EMPTY_PATH: typing.Final = 4096
