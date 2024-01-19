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
print(my_cgroups)

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

with tempfile.NamedTemporaryFile(mode="rt") as tmp:
    execution = runexecutor.execute_run(
        ["sh", "-c", f"sleep {wait}; cat /proc/self/cgroup"],
        tmp.name,
        memlimit=1024 * 1024,  # set memlimit to force check for swapaccount
        # set cores and memory_nodes to force usage of CPUSET
        cores=cores,
        memory_nodes=mems,
    )
    print("memory: {} MiB".format(execution.get("memory") / (1024**2)))
    assert execution.get("exitcode").raw == 0, execution.get("terminationreason")

    lines = []
    for line in tmp:
        line = line.strip()
        if (
            line
            and not line == f"sh -c 'sleep {wait}; cat /proc/self/cgroup'"
            and not all(c == "-" for c in line)
        ):
            lines.append(line)

    print(lines)

    task_cgroups = Cgroups.from_system(cgroup_procinfo=lines)

    fail = False
    expected_subsystems = [my_cgroups.FREEZE]
    if my_cgroups.version == 1:
        expected_subsystems += [my_cgroups.CPU, my_cgroups.CPUSET, my_cgroups.MEMORY]
    for subsystem in expected_subsystems:
        if subsystem in my_cgroups:
            if not str(task_cgroups[subsystem]).startswith(str(my_cgroups[subsystem])):
                logging.warning(
                    "Task was in cgroup %s for subsystem %s, "
                    "which is not the expected sub-cgroup of %s. "
                    "Maybe some other program is interfering with cgroup management?",
                    task_cgroups[subsystem],
                    subsystem,
                    my_cgroups[subsystem],
                )
                fail = True
    if fail:
        sys.exit(1)
