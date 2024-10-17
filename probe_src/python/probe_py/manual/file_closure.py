import shlex
import rich.console
import typer
import subprocess
import tempfile
import shutil
import warnings
import pathlib
import typing
from probe_py.generated.parser import ProvLog, InodeVersionLog
from probe_py.generated.ops import Path, ChdirOp, OpenOp, CloseOp, InitProcessOp, ExecOp
from .consts import AT_FDCWD


def build_oci_image(
        prov_log: ProvLog,
        image_name: str,
        push_docker: bool,
        verbose: bool,
        console: rich.console.Console,
) -> None:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        copy_file_closure(
            prov_log,
            tmpdir,
            copy=False,
            verbose=verbose,
            console=console,
        )
        # TODO: smartly show errors when shelling out to $cmd fails.
        if not shutil.which("buildah"):
            console.print("Buildah not found; should be included in probe-bundled? for other packages, please install Buildah separately", style="red")
            raise typer.Exit(code=1)
        container_id = subprocess.run(
            ["buildah", "from", "scratch"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if verbose:
            console.print(f"Container ID: {container_id}")
        subprocess.run(
            ["buildah", "copy", container_id, str(tmpdir), "/"],
            check=True,
            capture_output=not verbose,
            text=True,
        )
        pid = get_root_pid(prov_log)
        if pid is None:
            console.print("Could not find root process; Are you sure this probe_log is valid?")
            raise typer.Exit(code=1)
        last_op = prov_log.processes[pid].exec_epochs[0].threads[pid].ops[-1].data
        if not isinstance(last_op, ExecOp):
            console.print("Last op is not ExecOp. Are you sure this probe_log is valid?")
            raise typer.Exit(code=1)
        args = [
            arg.decode() for arg in last_op.argv
        ]
        subprocess.run(
            ["buildah", "config", "--cmd", shlex.join(args), container_id],
            check=True,
            capture_output=not verbose,
            text=True,
        )
        subprocess.run(
            ["buildah", "commit", container_id, image_name],
            check=True,
            capture_output=not verbose,
            text=True,
        )
        if push_docker:
            subprocess.run(
            ["buildah", "push", image_name, f"docker_daemon:{image_name}"],
                check=True,
                capture_output=not verbose,
                text=True,
            )


def copy_file_closure(
        prov_log: ProvLog,
        destination: pathlib.Path,
        copy: bool,
        verbose: bool,
        console: rich.console.Console,
) -> None:
    """Extract files used by the application recoreded in prov_log to destination

    If the required file are recorded in prov_log, we will use that.
    However, prov_log only captures files that get mutated _during the $cmd_.
    We assume the rest of the files will not change between the time of `probe record $cmd` and `probe oci-image`.
    (so probably run those back-to-back).
    For the files not included in prov_log, we will use the current copy on-disk.
    However, we will test to ensure it is the same version as recorded in prov_log.

    `copy` refers to whether we should copy files from disk or symlink them.
    """

    for pid, process in prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            pid = get_root_pid(prov_log)
            if pid is None:
                console.print("Could not find root process; Are you sure this probe_log is valid?")
                raise typer.Exit(code=1)
            first_op = prov_log.processes[pid].exec_epochs[0].threads[pid].ops[0].data
            if not isinstance(first_op, InitProcessOp):
                console.print("First op is not InitProcessOp. Are you sure this probe_log is valid?")
                raise typer.Exit(code=1)
            fds = {AT_FDCWD: pathlib.Path(first_op.cwd.path.decode())}
            for tid, thread in exec_epoch.threads.items():
                for op in thread.ops:
                    if isinstance(op.data, ChdirOp):
                        path = op.data.path
                        resolved_path = resolve_path(fds, path)
                        fds[AT_FDCWD] = resolved_path
                        ivl = InodeVersionLog(
                            path.device_major,
                            path.device_minor,
                            path.inode,
                            path.mtime.sec,
                            path.mtime.nsec,
                            path.size,
                        )
                        assert resolved_path.is_absolute()
                        destination_path = destination / resolved_path.relative_to("/")
                        destination_path.parent.mkdir(exist_ok=True, parents=True)
                        if inode_content := prov_log.inodes[ivl]:
                            # These inodes are "owned" by us, since we extracted them from the tar archive.
                            # When the tar archive gets deleted, these inodes will remain.
                            destination_path.hardlink_to(inode_content)
                            if verbose:
                                console.print(f"Hardlinking {resolved_path} from prov_log")
                        if resolved_path.exists():
                            if InodeVersionLog.from_path(resolved_path) != ivl:
                                warnings.warn(f"{resolved_path} changed in between the time of `probe record` and now.")
                            if copy:
                                if verbose:
                                    console.print(f"Copying {resolved_path} from disk")
                                shutil.copyfile(resolved_path, destination_path)
                            else:
                                if verbose:
                                    console.print(f"Hardlinking {resolved_path} from disk")
                                destination_path.hardlink_to(resolved_path)
                        else:
                            raise Exception(f"{resolved_path} disappeared since `probe record`")
                    elif isinstance(op.data, OpenOp):
                        fds[op.data.fd] = resolve_path(fds, op.data.path)
                    elif isinstance(op.data, CloseOp):
                        for fd in range(op.data.low_fd, op.data.high_fd + 1):
                            if fd in fds:
                                del fds[fd]


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


def get_root_pid(prov_log: ProvLog) -> int | None:
    for pid, process in prov_log.processes.items():
        first_op = process.exec_epochs[0].threads[pid].ops[0].data
        if isinstance(first_op, InitProcessOp) and first_op.is_root:
            return pid
    return None
