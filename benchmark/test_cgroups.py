# This file is part of BenchExec, a framework for reliable benchmarking:
# https://github.com/sosy-lab/benchexec
#
# SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
import sys
import tempfile
import pathlib

from benchexec.cgroups import Cgroups
from benchexec.runexecutor import RunExecutor

wait = 1

sys.dont_write_bytecode = True  # prevent creation of .pyc files

logging.basicConfig(format="%(levelname)s: %(message)s")
runexecutor = RunExecutor(use_namespaces=False)
my_cgroups = runexecutor.cgroups

if not (
    my_cgroups.CPU in my_cgroups
    # and FREEZER in my_cgroups # For now, we do not require freezer
    and my_cgroups.MEMORY in my_cgroups
):
    sys.exit(1)

if my_cgroups.CPUSET in my_cgroups:
    cores = my_cgroups.read_allowed_cpus()
    mems = my_cgroups.read_allowed_memory_banks()
else:
    # Use dummy value (does not matter which) to let execute_run() fail.
    cores = [0]
    mems = [0]

s = runexecutor.execute_run(
    ["sh", "-c", f"sleep {wait}; cat /proc/self/cgroup"],
    "/dev/stdout",
    memlimit=1024 * 1024,  # set memlimit to force check for swapaccount
    # set cores and memory_nodes to force usage of CPUSET
    cores=cores,
    memory_nodes=mems,
)
print(s.get("terminationreason"), s.get("memory") / (1024**2))
