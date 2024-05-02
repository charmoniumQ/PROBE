from __future__ import annotations
import dataclasses
import shlex
import os
import pathlib
import tempfile
import subprocess
import shutil


pwd = pathlib.Path().resolve()
AT_FDCWD = -100
NULL_FD = -1
NULL_MODE = -1
NULL_INODE = -1
NULL_DEVICE_MAJOR = -1
NULL_DEVICE_MINOR = -1
_head = shutil.which("head")
assert _head
head = pathlib.Path(_head)


class Sentinel:
    def __repr__(self) -> str:
        return self.__class__.__name__ + "()"


class MatchAny(Sentinel):
    pass


class MatchPositive(Sentinel):
    pass


@dataclasses.dataclass
class Op:
    op_code: str # not worth making an enum yet
    fd: int | None | MatchPositive
    dirfd: int | None
    mode: int | None
    inode: int | None | MatchPositive
    device_major: int | None | MatchAny
    device_minor: int | None | MatchAny
    path: pathlib.Path | None

    @staticmethod
    def parse_prov_log_dir(prov_log_path: pathlib.Path) -> tuple[Op, ...]:
        output = list[Op]()
        for child in sorted(prov_log_path.iterdir()):
            output.extend(Op.parse_prov_log_file(child))
        return tuple(output)

    @staticmethod
    def parse_prov_log_file(prov_log_file: pathlib.Path) -> tuple[Op, ...]:
        output = list[Op]()
        for line in prov_log_file.read_text().split("\0"):
            if line.startswith("\n"):
                line = line[1:]
            if line:
                op_code, fd, dirfd, mode, inode, device_major, device_minor, path = line.split(" ")
                output.append(Op(op_code, int(fd), int(dirfd), int(mode), int(inode), int(device_major), int(device_minor), pathlib.Path(path) if path else None))
        return tuple(output)


def match_list(actual_ops: tuple[Op, ...], expected_ops: tuple[Op | MatchAny, ...]):
    assert len(actual_ops) == len(expected_ops)
    expected_op_index = 0
    for actual_op, expected_op in zip(actual_ops, expected_ops):
        print("Actual:", actual_op)
        # print("Expected:", expected_op)
        if not isinstance(expected_op, MatchAny):
            assert actual_op.op_code == expected_op.op_code
            assert (isinstance(expected_op.fd, MatchPositive) and isinstance(actual_op.fd, int) and actual_op.fd > 0) or actual_op.fd == expected_op.fd
            assert actual_op.dirfd == expected_op.dirfd
            assert (isinstance(expected_op.inode, MatchPositive) and isinstance(actual_op.inode, int) and actual_op.inode > 0) or actual_op.inode == expected_op.inode
            assert isinstance(expected_op.device_major, MatchAny) or actual_op.device_major == expected_op.device_major
            assert isinstance(expected_op.device_minor, MatchAny) or actual_op.device_minor == expected_op.device_minor
            assert actual_op.path == expected_op.path


def run_command_with_prov(
        cmd: tuple[str, ...],
        verbose: bool = False,
) -> tuple[Op, ...]:
    with tempfile.TemporaryDirectory() as _prov_log_dir:
        prov_log_dir = pathlib.Path(_prov_log_dir)
        print("\n$ " + shlex.join(cmd))
        subprocess.run(
            cmd,
            env={
                **os.environ,
                "LD_PRELOAD": f"{pwd}/libprov.so",
                "PROV_LOG_DIR": str(prov_log_dir),
                "PROV_LOG_VERBOSE": "1" if verbose else "",
            },
            check=True,
            capture_output=False,
        )
        print()
        return Op.parse_prov_log_dir(prov_log_dir)


def close_op(fd: int | MatchPositive) -> Op:
    return Op(
        op_code='Close',
        fd=fd,
        dirfd=NULL_FD,
        inode=NULL_INODE,
        mode=NULL_MODE,
        device_major=NULL_DEVICE_MAJOR,
        device_minor=NULL_DEVICE_MINOR,
        path=None,
    )

def open_ops(op_code: str, dirfd: int, fd: int | MatchPositive, path: pathlib.Path) -> tuple[Op, ...]:
    return (
        Op(
            op_code='MetadataRead',
            fd=NULL_FD,
            dirfd=dirfd,
            inode=MatchPositive(),
            mode=NULL_MODE,
            device_major=MatchAny(),
            device_minor=MatchAny(),
            path=path,
        ),
        Op(
            op_code=op_code,
            fd=fd,
            dirfd=dirfd,
            inode=MatchPositive(),
            mode=NULL_MODE,
            device_major=MatchAny(),
            device_minor=MatchAny(),
            path=path,
        ),
    )

def isatty_ops(fd: int | MatchPositive) -> tuple[Op, ...]:
    return (*open_ops("OpenReadWrite", AT_FDCWD, fd, pathlib.Path("/dev/tty")), close_op(3))


def test_head() -> None:
    match_list(
        run_command_with_prov(("head", "--bytes=5", "flake.nix")),
        (
            *open_ops("OpenRead", AT_FDCWD, 3, pathlib.Path('flake.nix')),
            close_op(3),
        ),
    )


def test_shell() -> None:
    match_list(
        run_command_with_prov(("bash", "-c", "head --bytes=5 flake.nix")),
        (
            *isatty_ops(3),
            Op(op_code='Execute', fd=NULL_FD, dirfd=AT_FDCWD, inode=MatchPositive(), mode=NULL_MODE, device_major=MatchAny(), device_minor=MatchAny(), path=head),
            *open_ops("OpenRead", AT_FDCWD, 3, pathlib.Path('flake.nix')),
            close_op(3),
        )
    )


def test_chdir() -> None:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        file = tmpdir / "flake.nix"
        file.write_text("hello\n")
        match_list(
            run_command_with_prov(("bash", "-c", f"head --bytes=5 flake.nix; cd {tmpdir!s}; head --bytes=5 flake.nix")),
            (
                *isatty_ops(3),
                Op(op_code='Chdir', fd=NULL_FD, dirfd=AT_FDCWD, inode=MatchPositive(), mode=NULL_MODE, device_major=MatchAny(), device_minor=MatchAny(), path=tmpdir),
                Op(op_code='Execute', fd=NULL_FD, dirfd=AT_FDCWD, inode=MatchPositive(), mode=NULL_MODE, device_major=MatchAny(), device_minor=MatchAny(), path=head),
                *open_ops("OpenRead", AT_FDCWD, 3, pathlib.Path('flake.nix')),
                close_op(3),
                *isatty_ops(3),
                Op(op_code='Execute', fd=NULL_FD, dirfd=AT_FDCWD, inode=MatchPositive(), mode=NULL_MODE, device_major=MatchAny(), device_minor=MatchAny(), path=head),
                *open_ops("OpenRead", AT_FDCWD, 3, pathlib.Path('flake.nix')),
                close_op(3),
            )
        )
