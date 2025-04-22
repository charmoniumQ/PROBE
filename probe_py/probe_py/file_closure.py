import random
import os
import re
import shlex
import rich.console
import typer
import subprocess
import tempfile
import shutil
import warnings
import pathlib
import typing
from .ptypes import ProbeLog, initial_exec_no, Inode, InodeVersion
from .ops import Path, ChdirOp, OpenOp, CloseOp, InitProcessOp, ExecOp
from .consts import AT_FDCWD


def build_oci_image(
        probe_log: ProbeLog,
        image_name: str,
        push_docker: bool,
        verbose: bool,
        console: rich.console.Console,
) -> None:
    root_pid = get_root_pid(probe_log)
    if root_pid is None:
        console.print("Could not find root process; Are you sure this probe_log is valid?")
        raise typer.Exit(code=1)
    first_op = probe_log.processes[root_pid].execs[initial_exec_no].threads[root_pid.main_thread()].ops[0].data
    if not isinstance(first_op, InitProcessOp):
        console.print("First op is not InitProcessOp. Are you sure this probe_log is valid?")
        raise typer.Exit(code=1)
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        copy_file_closure(
            probe_log,
            tmpdir,
            copy=True,
            verbose=verbose,
            console=console,
        )
        # TODO: smartly show errors when shelling out to $cmd fails.
        if not shutil.which("buildah"):
            console.print("Buildah not found; should be included in probe-bundled? for other packages, please install Buildah separately", style="red")
            raise typer.Exit(code=1)

        # Start contianer
        container_id = f"probe-{random.randint(0, 2**32 - 1):08x}"
        if verbose:
            console.print(shlex.join(["buildah", "from", "--name", container_id, "scratch"]))
        subprocess.run(
            ["buildah", "from", "--name", container_id, "scratch"],
            check=True,
            capture_output=not verbose,
            text=True,
        )

        # Copy relevant files
        if verbose:
            console.print(shlex.join(["buildah", "copy", container_id, str(tmpdir), "/"]))
        subprocess.run(
            ["buildah", "copy", container_id, str(tmpdir), "/"],
            check=True,
            capture_output=not verbose,
            text=True,
        )

        # Set up other config (env, cmd, entrypoint)
        pid = get_root_pid(probe_log)
        if pid is None:
            console.print("Could not find root process; Are you sure this probe_log is valid?")
            raise typer.Exit(code=1)
        last_op = probe_log.processes[pid].execs[initial_exec_no].threads[pid.main_thread()].ops[-1].data
        if not isinstance(last_op, ExecOp):
            console.print(f"Last op is not ExecOp: {last_op}. Are you sure this probe_log is valid?")
            raise typer.Exit(code=1)
        args = [
            arg.decode() for arg in last_op.argv
        ]
        env = []
        for key_val in last_op.env:
            if not key_val.startswith(b"LD_PRELOAD="):
                if b"$" in key_val:
                    # TODO: figure out how to escape money
                    console.log(f"Skipping {key_val.decode(errors='surrogate')} because $ confuses Buildah.")
                    continue
                env.append("--env")
                env.append(key_val.decode(errors="surrogate"))
        #shell = pathlib.Path(os.environ["SHELL"]).resolve()
        cmd = [
            "buildah",
            "config",
            "--workingdir",
            first_op.cwd.path.decode(),
            "--cmd",
            shlex.join(args),
            *env,
            container_id,
        ]
        if verbose:
            console.print(shlex.join(cmd))
        subprocess.run(
            cmd,
            check=True,
            capture_output=not verbose,
            text=True,
        )

        # Commit (exports OCI image; podman can read it from here)
        cmd = ["buildah", "commit", container_id, image_name]
        if verbose:
            print(cmd)
        subprocess.run(
            cmd,
            check=True,
            capture_output=not verbose,
            text=True,
        )

        # Export to docker, if requested
        if push_docker:
            cmd = ["buildah", "push", image_name, f"docker-daemon:{image_name}"]
            if verbose:
                console.log(shlex.join(cmd))
            subprocess.run(
                cmd,
                check=True,
                capture_output=not verbose,
                text=True,
            )


def copy_file_closure(
        probe_log: ProbeLog,
        destination: pathlib.Path,
        copy: bool,
        verbose: bool,
        console: rich.console.Console,
) -> None:
    """Extract files used by the application recoreded in probe_log to destination

    If the required file are recorded in probe_log, we will use that.
    However, probe_log only captures files that get mutated _during the $cmd_.
    We assume the rest of the files will not change between the time of `probe record $cmd` and `probe oci-image`.
    (so probably run those back-to-back).
    For the files not included in probe_log, we will use the current copy on-disk.
    However, we will test to ensure it is the same version as recorded in probe_log.

    `copy` refers to whether we should copy files from disk or symlink them.
    """

    to_copy = dict[pathlib.Path, Path | None]()
    to_copy_exes = dict[pathlib.Path, Path | None]()
    for pid, process in probe_log.processes.items():
        for exec_epoch_no, exec_epoch in process.execs.items():
            root_pid = get_root_pid(probe_log)
            if root_pid is None:
                console.print("Could not find root process; Are you sure this probe_log is valid?")
                raise typer.Exit(code=1)
            first_op = probe_log.processes[root_pid].execs[initial_exec_no].threads[root_pid.main_thread()].ops[0].data
            if not isinstance(first_op, InitProcessOp):
                console.print("First op is not InitProcessOp. Are you sure this probe_log is valid?")
                raise typer.Exit(code=1)
            fds = {AT_FDCWD: pathlib.Path(first_op.cwd.path.decode())}
            for tid, thread in exec_epoch.threads.items():
                for op_no, op in enumerate(thread.ops):
                    if isinstance(op.data, ChdirOp):
                        path = op.data.path
                        resolved_path = resolve_path(fds, path)
                        fds[AT_FDCWD] = resolved_path
                        if verbose:
                            console.print(f"chdir {resolved_path}")
                        assert resolved_path.is_absolute()
                    elif isinstance(op.data, OpenOp):
                        path = op.data.path
                        if op.data.ferrno == 0:
                            resolved_path = resolve_path(fds, path)
                            fds[op.data.fd] = resolved_path
                            to_copy[resolved_path] = path
                    elif isinstance(op.data, ExecOp):
                        path = op.data.path
                        if op.data.ferrno == 0:
                            resolved_path = resolve_path(fds, path)
                            to_copy_exes[resolved_path] = path
                    elif isinstance(op.data, CloseOp):
                        for fd in range(op.data.low_fd, op.data.high_fd + 1):
                            if fd in fds:
                                del fds[fd]

    shell = pathlib.Path(os.environ["SHELL"])
    to_copy_exes[shell] = None

    # For executables, we also have to use LDD to get the rqeuried dyn libs
    # There is a task in tasks.md for pushing this into libprobe the same way we do for searching for executables on $PATH.
    for resolved_path, maybe_path in to_copy_exes.items():
        to_copy[resolved_path] = maybe_path
        dependent_dlibs = set[str]()
        _get_dlibs(resolved_path, dependent_dlibs)
        for dependent_dlib in dependent_dlibs:
            to_copy[pathlib.Path(dependent_dlib)] = None
    inodes = probe_log.inodes
    if inodes is None:
        raise ValueError("PROBE log appears to not contain inodes")
    for resolved_path, maybe_path in to_copy.items():
        destination_path = destination / resolved_path.relative_to("/")
        destination_path.parent.mkdir(exist_ok=True, parents=True)
        if maybe_path is not None:
            ino_ver = InodeVersion(
                Inode(
                    probe_log.host,
                    maybe_path.device_major,
                    maybe_path.device_minor,
                    maybe_path.inode,
                ),
                maybe_path.mtime.sec,
                maybe_path.mtime.nsec,
                maybe_path.size,
            )
        else:
            ino_ver = None
        if ino_ver is not None and (inode_content := inodes.get(ivl)) is not None:
            # These inodes are "owned" by us, since we extracted them from the tar archive.
            # When the tar archive gets deleted, these inodes will remain.
            destination_path.hardlink_to(inode_content)
            if verbose:
                console.print(f"Hardlinking {resolved_path} from probe_log")
        elif any(resolved_path.is_relative_to(forbidden_path) for forbidden_path in forbidden_paths):
            if verbose:
                console.print(f"Skipping {resolved_path}")
        elif resolved_path.exists():
            if ino_ver is not None and InodeVersion.from_path(resolved_path) != ino_ver:
                warnings.warn(f"{resolved_path} changed in between the time of `probe record` and now.")
            if resolved_path.is_dir():
                destination_path.mkdir(exist_ok=True, parents=True)
            elif copy:
                if verbose:
                    console.print(f"Copying {resolved_path} from disk")
                shutil.copy2(resolved_path, destination_path)
            else: # not directory and hardlink
                if verbose:
                    console.print(f"Hardlinking {resolved_path} from disk")
                destination_path.hardlink_to(resolved_path)
        else:
            raise Exception(f"{resolved_path} disappeared since `probe record`")


def resolve_path(
        fds: typing.Mapping[int, pathlib.Path],
        path: Path,
) -> pathlib.Path:
    if path.path.startswith(b"/"):
        return pathlib.Path(path.path.decode()) # what a mouthful
    elif dir_path := fds.get(path.dirfd):
        return dir_path / pathlib.Path(path.path.decode())
    else:
        raise KeyError(f"dirfd {path.dirfd} not found in fd table")


def get_root_pid(probe_log: ProbeLog) -> int | None:
    possible_root = []
    for pid, process in probe_log.processes.items():
        first_op = process.execs[0].threads[pid].ops[0].data
        if isinstance(first_op, InitProcessOp):
            possible_root.append(pid)
    if possible_root:
        # TODO: Fix this; min works for Linux because PIDs are assigned sequentially
        return min(possible_root)
    else:
        return None


ldd_regex = re.compile(r"\s+(?P<path>/[a-zA-Z0-9./-]+)\s+")
ldd = shutil.which("ldd")

def _get_dlibs(exe_or_dlib: pathlib.Path, found: set[str]) -> None:
    if not ldd:
        raise ValueError("ldd not found")
    proc = subprocess.run(
        [ldd, str(exe_or_dlib)],
        text=True,
        capture_output=True,
        check=True,
    )
    for match in ldd_regex.finditer(proc.stdout):
        path = match.group("path")
        if path is not None and path not in found:
            found.add(path)
            _get_dlibs(exe_or_dlib, found)


forbidden_paths = [
    pathlib.Path("/dev"),
    pathlib.Path("/proc"),
    pathlib.Path("/sys"),
]
