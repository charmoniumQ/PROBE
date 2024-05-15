from __future__ import annotations
import dataclasses
import shlex
import os
import pathlib
import typing
import tempfile
import subprocess
import shutil


pwd = pathlib.Path().resolve()
AT_FDCWD = -100
_head = shutil.which("head")
assert _head
head = pathlib.Path(_head)
NoneType = type(None)


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
    fd: int | None
    dirfd: int | None
    mode: int | None
    inode: int | None
    device_major: int | None
    device_minor: int | None
    path: pathlib.Path | None

    @staticmethod
    def parse_prov_log_dir(prov_log_path: pathlib.Path, verbose: bool = False) -> tuple[Op, ...]:
        output = list[Op]()
        for child in sorted(prov_log_path.iterdir()):
            if verbose:
                print(child)
            output.extend(Op.parse_prov_log_file(child, verbose))
        return tuple(output)

    @staticmethod
    def parse_prov_log_file(prov_log_file: pathlib.Path, verbose: bool) -> tuple[Op, ...]:
        output = list[Op]()
        for line in prov_log_file.read_text().split("\0"):
            if line.startswith("\n"):
                line = line[1:]
            if line:
                op_code, fd, dirfd, mode, inode, device_major, device_minor, path = line.split(" ")
                op = Op(
                    op_code,
                    int(fd) if fd != "-20" else None,
                    int(dirfd) if dirfd != "-20" else None,
                    int(mode) if mode != "-20" else None,
                    int(inode) if inode != "-20" else None,
                    int(device_major) if device_major != "-20" else None,
                    int(device_minor) if device_minor != "-20" else None,
                    pathlib.Path(path) if path else None,
                )
                if verbose:
                    print(op.op_code, end=" ")
                    if op.fd:
                        print(op.fd, end=" ")
                    if op.path:
                        print(op.path, end=" ")
                    print()
                output.append(op)
        return tuple(output)


@dataclasses.dataclass
class OpTemplate:
    op_code: str # not worth making an enum yet
    fd: int | None | MatchPositive
    dirfd: int | None
    mode: int | None
    inode: int | None | MatchPositive
    device_major: int | None | MatchAny
    device_minor: int | None | MatchAny
    path: pathlib.Path | None
    optional: bool = False

    @staticmethod
    def match(actual_op: Op, expected_op: OpTemplate) -> tuple[None, None, None] | tuple[str, typing.Any, typing.Any]:
        if actual_op.op_code != expected_op.op_code:
            return ("op_code", actual_op.op_code, expected_op.op_code)
        elif (isinstance(expected_op.fd, (int, NoneType)) and actual_op.fd != expected_op.fd) or (isinstance(expected_op.fd, MatchPositive) and (not isinstance(actual_op.fd, int) or actual_op.fd <= 0)):
            return ("fd", actual_op.fd, expected_op.fd)
        elif actual_op.dirfd != expected_op.dirfd:
            return ("dirfd", actual_op.dirfd, expected_op.dirfd)
        elif (isinstance(expected_op.inode, (int, NoneType)) and actual_op.inode != expected_op.inode) or (isinstance(expected_op.inode, MatchPositive) and (not isinstance(actual_op.inode, int) or actual_op.inode <= 0)):
            return ("inode", actual_op.inode, expected_op.inode)
        elif (isinstance(expected_op.device_major, (int, NoneType)) and actual_op.device_major != expected_op.device_major):
            return ("device_major", actual_op.device_major, expected_op.device_major)
        elif (isinstance(expected_op.device_minor, (int, NoneType)) and actual_op.device_minor != expected_op.device_minor):
            return ("device_minor", actual_op.device_minor, expected_op.device_minor)
        elif actual_op.path != expected_op.path:
            return ("path", actual_op.path, expected_op.path)
        else:
            return (None, None, None)

    @staticmethod
    def match_list(
            actual_ops: tuple[Op, ...],
            expected_ops: tuple[OpTemplate | MatchAny, ...],
            verbose: bool = False,
    ) -> tuple[int, int, str, typing.Any, typing.Any] | tuple[None, None, None, None, None]:
        actual_op_index = 0
        expected_op_index = 0
        while actual_op_index < len(actual_ops):
            actual_op = actual_ops[actual_op_index]
            if expected_op_index >= len(expected_ops):
                return (actual_op_index, expected_op_index, "exhausted expected ops", None, None)
            expected_op = expected_ops[expected_op_index]
            if isinstance(expected_op, MatchAny):
                expected_op_index += 1
                actual_op_index += 1
                if verbose:
                    print(f"expected_ops[{expected_op_index}] ~ actual_ops[{actual_op_index}] (MatchAny)")
            elif isinstance(expected_op, OpTemplate):
                prop, actual_val, expected_val = OpTemplate.match(actual_op, expected_op)
                if prop is None:
                    # Match
                    if verbose:
                        print(f"expected_ops[{expected_op_index}] ~ actual_ops[{actual_op_index}] ({actual_op.op_code})")
                    expected_op_index += 1
                    actual_op_index += 1
                elif expected_op.optional:
                    # No match, but expected was optional
                    if verbose:
                        print(f"expected_ops[{expected_op_index}] (optional {expected_op.op_code}) ~ actual_ops[{actual_op_index}] ({actual_op.op_code})")
                    expected_op_index += 1
                else:
                     # No match, not optional; must fail
                    if verbose:
                        print(f"expected_ops[{expected_op_index}] ({expected_op.op_code}) !~ actual_ops[{actual_op_index}] ({actual_op.op_code})")
                    return (actual_op_index, expected_op_index, prop, actual_val, expected_val)
            else:
                raise TypeError()
        return (None, None, None, None, None)

    @staticmethod
    def assert_match_list(
            actual_ops: tuple[Op, ...],
            expected_ops: tuple[OpTemplate | MatchAny, ...],
    ) -> None:
        actual_op_index, expected_op_index, prop, actual, expected = OpTemplate.match_list(actual_ops, expected_ops)
        if prop:
            for i, op in enumerate(actual_ops):
                print(i, op)
            for i, op2 in enumerate(expected_ops):
                print(i, op2)
        assert prop is None, (actual_op_index, expected_op_index, prop, actual, expected)

def run_command_with_prov(
        cmd: tuple[str, ...],
        verbose: bool = False,
) -> tuple[Op, ...]:
    with tempfile.TemporaryDirectory() as _prov_log_dir:
        prov_log_dir = pathlib.Path(_prov_log_dir)
        print(f"\n$ LD_PRELOAD={pwd}/libprov.so " + shlex.join(cmd))
        proc = subprocess.run(
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
        print(proc.returncode)
        print()
        return Op.parse_prov_log_dir(prov_log_dir)


def close_op(fd: int | MatchPositive) -> OpTemplate:
    return OpTemplate(
        op_code='Close',
        fd=fd,
        dirfd=None,
        inode=None,
        mode=None,
        device_major=None,
        device_minor=None,
        path=None,
    )

def open_ops(op_code: str, dirfd: int, fd: int | MatchPositive, path: pathlib.Path) -> tuple[OpTemplate, ...]:
    return (
        OpTemplate(
            op_code='MetadataRead',
            fd=None,
            dirfd=dirfd,
            inode=MatchPositive(),
            mode=None,
            device_major=MatchAny(),
            device_minor=MatchAny(),
            path=path,
        ),
        OpTemplate(
            op_code=op_code,
            fd=fd,
            dirfd=dirfd,
            inode=MatchPositive(),
            mode=None,
            device_major=MatchAny(),
            device_minor=MatchAny(),
            path=path,
        ),
    )


def optional_op(op: OpTemplate) -> OpTemplate:
    return dataclasses.replace(op, optional=True)


def initial_ops() -> tuple[OpTemplate, ...]:
    return (
        # isatty
        *open_ops("OpenReadWrite", AT_FDCWD, MatchPositive(), pathlib.Path("/dev/tty")),
        close_op(MatchPositive()),
        *map(optional_op, open_ops("OpenRead", AT_FDCWD, MatchPositive(), pathlib.Path("/lib/terminfo/x/xterm"))),
        optional_op(close_op(MatchPositive())),
    )


STDOUT_FILENO = 1
STDERR_FILENO = 2

def closing_ops() -> tuple[OpTemplate, ...]:
    return (
        optional_op(close_op(STDOUT_FILENO)),
        optional_op(close_op(STDERR_FILENO)),
    )


def test_head() -> None:
    OpTemplate.assert_match_list(
        run_command_with_prov(("head", "--bytes=5", "flake.nix")),
        (
            *open_ops("OpenRead", AT_FDCWD, MatchPositive(), pathlib.Path('flake.nix')),
            close_op(MatchPositive()),
            *closing_ops(),
        ),
    )


def test_shell() -> None:
    OpTemplate.assert_match_list(
        run_command_with_prov(("bash", "-c", "head --bytes=5 flake.nix")),
        (
            *initial_ops(),
            OpTemplate(op_code='Execute', fd=None, dirfd=AT_FDCWD, inode=MatchPositive(), mode=None, device_major=MatchAny(), device_minor=MatchAny(), path=head),
            *open_ops("OpenRead", AT_FDCWD, MatchPositive(), pathlib.Path('flake.nix')),
            close_op(MatchPositive()),
            *closing_ops(),
        ),
    )


def test_chdir() -> None:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        file = tmpdir / "flake.nix"
        file.write_text("hello\n")
        OpTemplate.assert_match_list(
            run_command_with_prov(("bash", "-c", f"head --bytes=5 flake.nix; cd {tmpdir!s}; head --bytes=5 flake.nix")),
            (
                *initial_ops(),
                OpTemplate(op_code='Execute', fd=None, dirfd=AT_FDCWD, inode=MatchPositive(), mode=None, device_major=MatchAny(), device_minor=MatchAny(), path=head),
                *open_ops("OpenRead", AT_FDCWD, MatchPositive(), pathlib.Path('flake.nix')),
                close_op(MatchPositive()),
                *closing_ops(),
                OpTemplate(op_code='Chdir', fd=None, dirfd=AT_FDCWD, inode=MatchPositive(), mode=None, device_major=MatchAny(), device_minor=MatchAny(), path=tmpdir),
                OpTemplate(op_code='Execute', fd=None, dirfd=AT_FDCWD, inode=MatchPositive(), mode=None, device_major=MatchAny(), device_minor=MatchAny(), path=head),
                *open_ops("OpenRead", AT_FDCWD, MatchPositive(), pathlib.Path('flake.nix')),
                close_op(MatchPositive()),
                *closing_ops(),
            ),
        )


def test_shell2() -> None:
    run_command_with_prov(("bash", "-c", "python -c 'print(4)'; head --bytes=5 flake.nix"))
