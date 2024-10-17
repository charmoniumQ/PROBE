import subprocess
import tempfile
import shutil
import warnings
import pathlib
import typing
from probe_py.generated.parser import ProvLog, InodeVersionLog
from probe_py.generated.ops import Path, ChdirOp, OpenOp, CloseOp, InitProcessOp
from .consts import AT_FDCWD


def build_oci_image(
        prov_log: ProvLog,
        image_name: str,
        push_docker: bool,
) -> None:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        copy_file_closure(
            prov_log,
            tmpdir,
            copy=False,
        )
        # TODO: smartly show errors when shelling out to $cmd fails.
        container_id = subprocess.run(
            ["buildah", "from", "scratch"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["buildah", "copy", container_id, str(tmpdir), "/"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["buildah", "commit", container_id, image_name],
            check=True,
            capture_output=True,
            text=True,
        )
        if push_docker:
            subprocess.run(
            ["buildah", "push", image_name, f"docker_daemon:{image_name}"],
                check=True,
                capture_output=True,
                text=True,
            )


def copy_file_closure(
        prov_log: ProvLog,
        prov_cwd: pathlib.Path,
        destination: pathlib.Path,
        copy: bool,
) -> None:
    for pid, process in prov_log.processes.items():
        first_op = process.exec_epochs[0].threads[pid].ops[0].data
        if isinstance(first_op, InitProcessOp) and first_op.proc_root:
            cwd = pathlib.Path(first_op.cwd.path)
            break
    else:
        raise RuntimeError("Root process not found. Are you sure this probe_log is valid?")
    for pid, process in prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            fds = {AT_FDCWD: cwd}
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
                        if resolved_path.exists():
                            if InodeVersionLog.from_path(resolved_path) != ivl:
                                warnings.warn(f"{resolved_path} changed in between the time of `probe record` and now.")
                            if copy:
                                shutil.copyfile(resolved_path, destination_path)
                            else:
                                destination_path.hardlink_to(resolved_path)
                        else:
                            raise Exception(f"{resolved_path} disappeared since `probe record`")
                    elif isinstance(op.data, OpenOp):
                        fds[op.data.fd] = resolve_path(fds, op.data.path)
                    elif isinstance(op.data, CloseOp):
                        del fds[op.data.fd]


def resolve_path(
        fds: typing.Mapping[int, pathlib.Path],
        path: Path,
) -> pathlib.Path:
    if path.path.startswith("/"):
        return pathlib.Path(path.path) # what a mouthful
    elif dir_path := fds.get(path.dirfd):
        return dir_path / pathlib.Path(path.path)
    else:
        raise KeyError(f"dirfd {path.dirfd} not found in fd table")
