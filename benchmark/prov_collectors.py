import shutil
import shlex
import dataclasses
import warnings
import subprocess
import os
import yaml
import tarfile
import re
from collections.abc import Sequence, Mapping
from pathlib import Path
from util import run_all, CmdArg, check_returncode, flatten1, to_str, SubprocessError, terminate_or_kill
from typing import Callable, cast, Any
from compound_pattern import CompoundPattern


# TODO: change ProvOperation.targets from str to Path
@dataclasses.dataclass(frozen=True)
class ProvOperation:
    type: str
    target0: str | None
    target1: str | None
    args: object | None


class ProvCollector:
    @property
    def requires_empty_dir(self) -> bool:
        return False

    def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
        return None

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return cmd

    def stop(self, env: Mapping[str, str]) -> None:
        pass

    def __str__(self) -> str:
        return self.name

    def count(self, log: Path, exe: Path) -> tuple[ProvOperation, ...]:
        return ()

    @property
    def name(self) -> str:
        return self.__class__.__name__.lower()

    @property
    def method(self) -> str:
        return "None"

    @property
    def submethod(self) -> str:
        return "None"

    @property
    def nix_packages(self) -> list[str]:
        return []


class NoProv(ProvCollector):
    name = "noprov"

libcalls = "-*+" + "+".join([
    # https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html
    "fopen", "fopen64", "freopen", "freopen64",
    # https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html
    "fclose", "fcloseall",
    # https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html
    "open", "open64", "creat", "creat64", "close", "close_range", "closefrom",
    # https://www.gnu.org/software/libc/manual/html_node/Descriptors-and-Streams.html
    "fdopen",
    # https://www.gnu.org/software/libc/manual/html_node/Duplicating-Descriptors.html
    "dup", "dup2",
    # https://www.gnu.org/software/libc/manual/html_node/Opening-a-Directory.html
    "opendir", "fdopendir", "readdir", "readdir_r", "readdir64", "readdir64_r",
    # https://www.gnu.org/software/libc/manual/html_node/Hard-Links.html
    "link", "linkat", "symlink", "symlinkat", "readlink", "readlinkat", "realpath",
    # https://www.gnu.org/software/libc/manual/html_node/Deleting-Files.html
    "unlink", "unlinkat", "rmdir", "remove",
    # https://www.gnu.org/software/libc/manual/html_node/Renaming-Files.html
    "rename", "renameat",
    # https://www.gnu.org/software/libc/manual/html_node/Creating-Directories.html
    "mkdir", "mkdirat",
    # https://www.gnu.org/software/libc/manual/html_node/Reading-Attributes.html
    "stat", "stat64", "fstat", "fstat64", "lstat", "lstat64",
    # https://www.gnu.org/software/libc/manual/html_node/File-Owner.html
    "chown", "fchown", "fchownat", "chown32", "lchown",
    # https://www.gnu.org/software/libc/manual/html_node/Setting-Permissions.html
    "chmod", "fchmod", "fchmodat",
    # https://www.gnu.org/software/libc/manual/html_node/Testing-File-Access.html
    "access", "faccessat",
    # https://www.gnu.org/software/libc/manual/html_node/File-Times.html
    "utimes", "lutimes", "futimes",
    "utime", "futimesat", "utimensat", "futimens"
    # https://www.gnu.org/software/libc/manual/html_node/File-Size.html
    "truncate", "truncate64", "ftruncate", "ftruncate64",
    # https://www.gnu.org/software/libc/manual/html_node/Making-Special-Files.html
    "mknod", "mknodat",
    # https://www.gnu.org/software/libc/manual/html_node/Temporary-Files.html
    "tmpfile", "tmpfile64", "mkstemp", "mkdtemp",
    # https://www.gnu.org/software/libc/manual/html_node/Creating-a-Pipe.html
    "pipe",
    # https://www.gnu.org/software/libc/manual/html_node/Pipe-to-a-Subprocess.html
    "popen", "pclose",
    # https://www.gnu.org/software/libc/manual/html_node/FIFO-Special-Files.html
    "mkfifo", "mkfifoat",
    # https://www.gnu.org/software/libc/manual/html_node/Setting-Address.html
    "bind",
    # https://www.gnu.org/software/libc/manual/html_node/Creating-a-Socket.html
    "socket",
    # https://www.gnu.org/software/libc/manual/html_node/Closing-a-Socket.html
    "shutdown",
    # https://ww.gnu.org/software/libc/manual/html_node/Socket-Pairs.html
    "socketpair",
    # https://www.gnu.org/software/libc/manual/html_node/Connecting.html
    "connect",
    # https://www.gnu.org/software/libc/manual/html_node/Listening.html
    "listen",
    # https://www.gnu.org/software/libc/manual/html_node/Accepting-Connections.html
    "accept",
    # TODO: send and receive, but don't log msg
    # https://www.gnu.org/software/libc/manual/html_node/Networks-Database.html
    "getnetbyname", "getnetbyaddr", "setnetent", "getnetent",
    # https://www.gnu.org/software/libc/manual/html_node/Running-a-Command.html
    "system",
    # https://www.gnu.org/software/libc/manual/html_node/Creating-a-Process.html
    "fork", "vfork",
    # https://www.gnu.org/software/libc/manual/html_node/Executing-a-File.html
    "execv", "execl", "execve", "fexecve", "execle", "execvp", "execlp",

    "getrandom",
    # modify f/open when target is /dev/u?random

    "gettimeofday",
    "mkstemp"

    # x86 instructions rdrand and rdseed

    # I'm pretty sure these should be here
    "clone", "chdir", "chroot", "fstatat", "dlopen", "dlclose",
])

syscalls = ",".join([
    # File syscalls
    "open", "openat", "openat2", "creat",
    "close", "close_range",
    "dup", "dup2", "dup3",
    "link", "linkat", "symlink", "symlinkat",
    "unlink", "unlinkat", "rmdir",
    "rename", "renameat",
    "mkdir", "mkdirat",
    "fstat", "newfstatat",
    "chown", "fchown", "lchown", "fchownat",
    "chmod", "fchmod", "fchmodat",
    "access", "faccessat",
    "utime", "utimes", "futimesat", "utimensat",
    "truncate", "ftruncate",
    "mknod", "mknodat",
    "readlink", "readlinkat",
    # TODO: Track fcntl and rerun results

    # sockets
    "bind", "accept", "accept4", "connect", "socketcall", "shutdown",

    # Other IPC
    "pipe", "pipe2",

    # xattr syscalls
    "fgetxattr", "flistxattr", "fremovexattr", "fsetxattr",
    "getxattr", "lgetxattr", "listxattr", "llistxattr",
    "lremovexattr", "lsetxattr", "removexattr", "setxattr",

    # Proc syscalls
    "clone", "clone3", "fork", "vfork",
    "execve", "execveat",
    "exit", "exit_group",
    "chroot", "fchdir", "chdir",
])


function_name = "[a-z0-9_.]+"


class AbstractTracer(ProvCollector):
    line_pattern: CompoundPattern
    group_processors: Mapping[str, Callable[[str], object]] = {}
    log_name: str
    use_get_dlib_on_exe: bool

    def _filter_op(self, op: ProvOperation) -> list[ProvOperation]:
        return [op]

    def count(self, log: Path, exe: Path) -> tuple[ProvOperation, ...]:
        log_contents = (log / self.log_name).read_text()
        operations = []
        def identity(obj):
            return obj
        if self.use_get_dlib_on_exe and is_executable_or_library(Path(exe)):
            for lib in get_dlibs(str(exe)):
                operations.append(ProvOperation("dldep", lib, None, {"source": exe}))
        for line in log_contents.split("\n"):
            if line.strip():
                line = line.strip()
                if (match := self.line_pattern.match(line)):
                    args = match.combined_groupdict()
                    op = args.get("op")
                    if op is not None:
                        operations.extend(self._filter_op(ProvOperation(
                            op,
                            args.get("target0"),
                            args.get("target1"),
                            {
                                key: self.group_processors.get(key, identity)(val)
                                for key, val in args.items()
                                if key not in {"target0", "target1", "op"}
                            },
                        )))
                else:
                    warnings.warn("Unable to parse line: " + line)
        return tuple(operations)


class STrace(AbstractTracer):
    method = "tracing"
    submethod = "syscalls"
    name = "strace"

    nix_packages = [".#strace"]

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return (
            "strace", "--follow-forks", "--trace", syscalls, "--output", log / self.log_name, "-s", f"{size}", *cmd,
        )

    # Log line example:
    # 5     execve("/paxoth/to/python", ...) = 0
    line_pattern = CompoundPattern(
        pattern=re.compile(r"^(?P<line>.*)$"),
        name="match-all",
        subpatterns={
            "line": [
                CompoundPattern(
                    name="call",
                    pattern=re.compile(r"^(?P<pid>\d+) +(?P<op>fname)\((?P<args>.*)(?:\) += (?P<ret>.*)| <unfinished ...>)$".replace("fname", function_name)),
                    subpatterns={
                        "args": [
                            CompoundPattern(
                                re.compile(r'^(?:(?P<before_args>[^"]*), )?"(?P<target0>[^"]*)", (?:(?P<between_args>[^"]*), )?"(?P<target1>[^"]*)"(?:, (?P<after_args>[^"]*))?$'),
                                name="2-str",
                            ),
                            CompoundPattern(
                                re.compile(r'^(?:(?P<before_args>[^"]*), )?"(?P<target0>[^"]*)"(?:, (?P<after_args>[^"]*))?$'),
                                name="1-str",
                            ),
                            CompoundPattern(
                                re.compile(r'^(?P<all_args>[^"]*)$'),
                                name="0-str",
                            ),
                            # Special case for execve:
                            CompoundPattern(
                                re.compile(r'^"(?P<target0>[^"]*)", (?P<after_args>\[.*\].*)$'),
                                name="execve",
                            ),
                            CompoundPattern(
                                re.compile(r"^(?P<before_struct>[^{]*), \{(?P<struct>.*?)\}, (?P<after_struct>.*)$"),
                                name="struct",
                                subpatterns={
                                    "struct": [
                                        CompoundPattern(
                                            re.compile(r'^(?:(?P<before_items>[^"]*), )?(?P<target0_key>[a-zA-Z0-9_]+)=[a-z_]*\(?"(?P<target0>[^"]*)"\)?(?:, (?P<after_items>[^"]*))?$'),
                                            name="struct-1-str",
                                        ),
                                        CompoundPattern(
                                            re.compile(r'^(?P<all_items>[^"]*)$'),
                                            name="struct-0-str",
                                        ),
                                    ],
                                }
                            ),
                        ],
                    },
                ),
                CompoundPattern(
                    re.compile(r"^(?P<pid>\d+) +<... (?P<op>fname) resumed>(?:, )?(?P<args>.*)\) += (?P<ret>.*)$".replace("fname", function_name)),
                    name="resumed",
                ),
                CompoundPattern(
                    re.compile(r"^(?P<pid>\d+) +\+\+\+ exited with (?P<exit_code>\d+) \+\+\+$"),
                    name="exit",
                ),
                CompoundPattern(
                    re.compile(r"^(?P<pid>\d+) +--- (?P<sig>SIG[A-Z0-9]+) \{(?P<sig_struct>.*)\} ---$"),
                    name="signal",
                ),
            ],
        },
    )
    use_get_dlib_on_exe = False
    group_processors = {
        "pid": int,
    }
    log_name = "strace.out"



ldd_regex = re.compile(r"\s+(?P<path>/[a-zA-Z0-9./-]+)\s+\(")

def _get_dlibs(exe_or_dlib: str, found: set[str]) -> None:
    env: Mapping[str, str] = {}
    proc = subprocess.run(
        ["ldd", exe_or_dlib],
        text=True,
        capture_output=True,
        env=env,
    )
    check_returncode(proc, env)
    for match in ldd_regex.finditer(proc.stdout):
        path = match.group("path")
        if path is not None and path not in found:
            found.add(path)
            _get_dlibs(exe_or_dlib, found)


def get_dlibs(exe_or_dlib: str) -> set[str]:
    ret = set[str]()
    _get_dlibs(exe_or_dlib, ret)
    return ret


class LTrace(AbstractTracer):
    method = "tracing"
    submethod = "libc calls"
    name = "ltrace"

    nix_packages = [".#ltrace", ".#glibc_bin", ".#coreutils"]

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return (
            "ltrace", "-f", "--config", "ltrace.conf.3", "-L", "-x", f"{libcalls}",
            "--output", log / self.log_name, "-s", f"{size}", "--", "env", *cmd,
        )

    def _filter_op(self, op: ProvOperation) -> list[ProvOperation]:
        if op.type is not None and (op.type.startswith("fopen") or op.type.startswith("open")):
            # For open calls, second argument is not a file! It's a mode.
            return [ProvOperation(
                type=op.type,
                target0=op.target0,
                target1=None,
                args={"mode": op.target1, **cast(Mapping[str, Any], op.args)},
            )]
        elif all([
                op.type is not None,
                op.type == "dlopen" or op.type.startswith("exec"),
                op.target0 is not None and is_executable_or_library(Path(op.target0)),
        ]):
            # For dlopen calls, we need to add the files dlopen(op.target0) will call
            return [
                op,
                *(
                    ProvOperation(type="dload_dep", target0=dlib, target1=None, args=None)
                    for dlib in get_dlibs(cast(str, op.target0))
                    if op.target0 is not None
                ),
            ]
        else:
            return [op]

    # Log line example:
    # 3 fstatat@libc.so.6(args)  = 0
    # 3 execv@libc.so.6(args <unfinished ...>
    # 3 execve@libc.so.6(args <no return ...>
    # 3 <... fstat resumed> )  = 0
    line_pattern = CompoundPattern(
        pattern=re.compile(r"^(?P<line>.*)$"),
        name="match-all",
        subpatterns={
            "line": [
                CompoundPattern(
                    pattern=re.compile(r"^(?P<pid>\d+) (?P<op>fname)@(?P<lib>[a-zA-Z0-9.-]*?)\((?P<args>.*?)(?:\) += (?P<ret>.*)|(?: <(?P<status>unfinished|no return) ...>))$".replace("fname", function_name)),
                    subpatterns={
                        "args": [
                            CompoundPattern(
                                pattern=re.compile(r'^(?:(?P<before_args>[^"]*), )?"(?P<target0>[^"]*)", (?:(?P<between_args>[^"]*), )?"(?P<target1>[^"]*)"(?:, (?P<after_args>[^"]*))?$'),
                                name="2-str",
                            ),
                            CompoundPattern(
                                pattern=re.compile(r'^(?:(?P<before_args>[^"]*), )?"(?P<target0>[^"]*)"(?:, (?P<after_args>[^"]*))?$'),
                                name="1-str",
                            ),
                            CompoundPattern(
                                pattern=re.compile(r'^(?P<all_args>[^"]*)$'),
                                name="0-str",
                            ),
                            CompoundPattern(
                                pattern=re.compile(r'^"(?P<target0>[^"]*)", \[(?P<cmd_args>.*)\]$'),
                                name="execvp",
                            ),
                        ],
                    },
                    name="call",
                ),
                CompoundPattern(
                    pattern=re.compile(r"^(?P<pid>\d+) <... (?P<op>fname) resumed> \) += (?P<ret>.*)$".replace("fname", function_name)),
                    name="resumed",
                ),
                CompoundPattern(
                    pattern=re.compile(r"^(?P<pid>\d+) --- Called (?P<op>fname)\(\) ---$".replace("fname", function_name)),
                    name="control-transferring-call",
                ),
                CompoundPattern(
                    pattern=re.compile(r"^(?P<pid>\d+) --- (?P<signal>SIG.+) ---$"),
                    name="signal",
                ),
                CompoundPattern(
                    pattern=re.compile(r"^(?P<pid>\d+) +\+\+\+ exited \(status (?P<exit_code>\d+)\) \+\+\+$"),
                    name="exit",
                ),
            ],
        },
    )
    use_get_dlib_on_exe = True
    group_processors = {
        "pid": int,
    }
    log_name = "ltrace.out"


PATH_MAX = os.pathconf('/', 'PC_PATH_MAX')
NAME_MAX = os.pathconf('/', 'PC_NAME_MAX')


def is_executable_or_library(path: Path) -> bool:
    if (
            len(path.name) < NAME_MAX and
            len(str(path)) < PATH_MAX and
            len(path.parts) > 1 and
            path.parts[1] not in {"sys", "proc", "dev"} and
            path.exists() and
            path.is_file()
    ):
        with path.open("rb") as fobj:
            try:
                return fobj.read(4) == b"b'\x7fELF"
            except Exception as exc:
                print(path)
                raise exc
    return False


class FSATrace(AbstractTracer):
    method = "lib instrm."
    submethod = "libc I/O"
    name = "fsatrace"
    log_name = "fsatrace.out"
    line_pattern = CompoundPattern(re.compile(r"^(?P<op>.)\|(?P<target0>[^|]*)(?:\|(?P<target1>.*))?$"))
    use_get_dlib_on_exe = True

    nix_packages = [".#fsatrace", ".#coreutils"]

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        (log / self.log_name).write_text("")
        return ("fsatrace", "rwmdqt", log / self.log_name, "--", "env", *cmd)

    def _filter_op(self, op: ProvOperation) -> list[ProvOperation]:
        operations = [op]
        if op.type == "r" and op.target0 is not None and is_executable_or_library(Path(op.target0)):
            for dlib in get_dlibs(op.target0):
                operations.append(ProvOperation("l", dlib, None, None))
        return operations


class PTU(ProvCollector):
    method = "ptrace"
    submethod = "syscalls"

    nix_packages = [".#provenance-to-use", ".#coreutils"]

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        assert log.is_dir()
        assert list(log.iterdir()) == []
        assert not log.is_absolute(), "This logic won't work to 'un-chdir' from log if log is absolute"
        undo_log_chdir = Path(*(len(log.parts) * [".."]))
        assert log.exists()
        return ("env", "--chdir", log, "ptu", "-o", ".", "env", "--chdir", undo_log_chdir, *cmd)

    def count(self, log: Path, exe: Path) -> tuple[ProvOperation, ...]:
        root = log / "cde-root"
        return tuple(
            ProvOperation("read", str(file.relative_to(root)), None, None)
            for file in root.glob("**")
        )


class CDE(ProvCollector):
    method = "ptrace"
    submethod = "syscalls"

    nix_packages = [".#cde"]

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        assert log.is_dir()
        assert list(log.iterdir()) == []
        return ("cde", "-o", log, *cmd)

    def count(self, log: Path, exe: Path) -> tuple[ProvOperation, ...]:
        root = log / "cde-root"
        return tuple(
            ProvOperation("read", str(file.relative_to(root)), None, None)
            for file in root.glob("**")
        )


class RR(ProvCollector):
    method = "ptrace"
    submethod = "syscalls"
    name = "rr"

    nix_packages = [".#rr", ".#coreutils"]

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        self.log = log
        return ("env", f"_RR_TRACE_DIR={self.log}", "rr", "record", *cmd)

    def stop(self, env: Mapping[str, str]) -> None:
        check_returncode(subprocess.run(
            ["rr", "pack", str(self.log / "latest-trace")],
            env=env,
            capture_output=True,
        ), env)


class ReproZip(ProvCollector):
    method = "ptrace"
    submethod = "syscalls"
    name = "reprozip"

    nix_packages = [".#reprozip"]

    def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
        check_returncode(subprocess.run(
            ["reprozip", "usage_report", "--disable"],
            check=False,
            capture_output=True,
            env=env,
        ), env)
        assert not (log / "reprozip").exists()

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return ("reprozip", "trace", "--dir", log / "reprozip", *cmd)

    def count(self, log: Path, exe: Path) -> tuple[ProvOperation, ...]:
        config = yaml.safe_load((log / "reprozip/config.yml").read_text())
        def n2l(lst):
            return [] if lst is None else lst
        files = n2l(config.get("other_files")) + list(flatten1(
            n2l(package.get("files"))
            for package in n2l(config.get("packages"))
        ))
        return tuple(
            ProvOperation("read", file, None, None)
            for file in files
        )


class Sciunit(ProvCollector):
    method = "ptrace"
    submethod = "syscalls"
    name = "sciunit"

    nix_packages = [".#sciunit2", ".#coreutils"]
    path = ""

    def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
        self.path = env["PATH"]
        check_returncode(subprocess.run(
            ["sciunit", "create", "-f", "test"],
            check=False,
            env={
                **env,
                "SCIUNIT_HOME": str(log.resolve()),
            },
        ), {})

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        cwd = Path().resolve()
        return (
            "sh",
            "-c",
            ";".join([
                # sciunit puts its copy of Python on PATH before the one we need.
                # So we will save the PATH and restore it
                "export _PATH=$PATH",
                f"cd {log.resolve()}",
                f"export SCIUNIT_HOME={log.resolve()}",
                f"sciunit exec env --chdir={cwd.resolve()} PATH=$_PATH {shlex.join(cmd)}"
            ]),
        )


class Darshan(ProvCollector):
    method = "lib instrm."
    submethod = "libc I/O"

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        raise NotImplementedError()


class BPFTrace(ProvCollector):
    method = "auditing"
    submethod = "eBPF"
    name = "bpftrace"
    proc: subprocess.Popen[bytes] | None = None
    proc_args: list[CmdArg] | None = None
    proc_env: Mapping[str, str] | None = None

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        raise NotImplementedError()

    def stop(self, env: Mapping[str, str]) -> None:
        raise NotImplementedError()

    def count(self, log: Path, exe: Path) -> tuple[ProvOperation, ...]:
        raise NotImplementedError()


class SpadeFuse(ProvCollector):
    _workdir: Path | None = None
    requires_empty_dir = True
    method = "FS instrm."
    submethod = "FUSE"
    name = "SPADE+FUSE"
    # echo -e "add reporter LinuxFUSE $PWD/test2\nadd storage Neo4j database=$PWD/spade.graph" | ./result/bin/spade control
    # echo -e "remove reporter LinuxFUSE\nremove storage Neo4j" | ./result/bin/spade control
    _start = "\n".join([
        "add reporter LinuxFUSE {workdir}",
        "add storage Neo4j database={log}/spade.graph",
        "add analyzer CommandLine",
    ])
    _stop = "\n".join([
        "remove reporter LinuxFUSE",
        "remove storage Neo4j",
    ])
    _query = "\n".join([
        "export > {log}/galileo.dot",
        "dump all",
    ])

    def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
        self._workdir = workdir
        # SPADE FUSE must start in a non-existant directory
        self._workdir.unlink()
        assert not self._workdir.exists()
        subprocess.run(
            ["spade", "start"],
            check=True,
            capture_output=True,
            env=env,
        )

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        assert self._workdir is not None
        subprocess.run(
            ["spade", "control"],
            check=True,
            capture_output=True,
            text=True,
            input=self._start.format(workdir=self._workdir, log=log),
        )
        return (
            "env", "--chdir", self._workdir, *cmd
        )

    def stop(self, env: Mapping[str, str]) -> None:
        subprocess.run(
            ["spade", "control"],
            check=True,
            capture_output=True,
            text=True,
            input=self._stop.format(),
            env=env,
        )


class SpadeAuditd(ProvCollector):
    method = "auditing"
    submethod = "auditd"
    name = "SPADE+Auditd"

    def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
        # https://github.com/ashish-gehani/SPADE/blob/b24daa56332e8478711bee80e5ac1f1558ff5e52/src/spade/reporter/audit/AuditControlManager.java#L57
        syscalls = ("fileIO=false", "netIO=true", "IPC=true")
        subprocess.run(["spade", "start"], check=True, capture_output=True, env=env)
        subprocess.run(["spade", "control", "add", "reporter", "Audit", *syscalls], check=True, capture_output=True, env=env)

    def stop(self, env: Mapping[str, str]) -> None:
        subprocess.run(
            ["spade", "stop"],
            check=True,
            capture_output=True,
            env=env,
        )


class Auditd(ProvCollector):
    method = "auditing"
    submethod = "auditd"

    def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
        raise NotImplementedError(
            "I want to trace specific syscalls before continuing"
        )

        # https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/7/html/security_guide/sec-defining_audit_rules_and_controls
        auditctl_rules = ()

        # Run instead of return this command.  That way, the command
        # will complete before we continue to testthe workload.  For
        # other auditors, the command would be running _concurrently_
        # to the workload.
        subprocess.run(
            run_all(
                ("auditctl", "-D"),
                ("auditctl", *auditctl_rules),
            ),
            check=True,
            env=env,
        )

    def stop(self, env: Mapping[str, str]) -> None:
        subprocess.run(["auditctl", "-D"], check=True, env=env)


class Care(ProvCollector):
    method = "tracing"
    submethod = "syscalls"
    name = "care"

    nix_packages = [".#care", ".#lzop"]

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return ("care", f"--output={log}/main.tar", "--revealed-path=tmp", "--revealed-path=/home/benchexec", "--verbose=-1", *cmd)

    def count(self, log: Path, exe: Path) -> tuple[ProvOperation, ...]:
        prefix = "main/rootfs"
        with tarfile.open(name=(log / "main.tar"), mode='r') as tar_obj:
            return tuple(
                ProvOperation("use", member.name[len(prefix):], None, None)
                for member in tar_obj.getmembers()
                if member.name.startswith(prefix)
            )


PROV_COLLECTORS: list[ProvCollector] = [
    NoProv(),
    STrace(),
    LTrace(),
    FSATrace(),
    CDE(),
    RR(),
    ReproZip(),
    Sciunit(),
    Care(),
    PTU(),
    SpadeFuse(),
    SpadeAuditd(),
    Darshan(),
    BPFTrace(),
]

PROV_COLLECTOR_GROUPS: Mapping[str, list[ProvCollector]] = {
    # Singleton groups
    **{
        prov_collector.name: [prov_collector]
        for prov_collector in PROV_COLLECTORS
    },
    "superfast": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in ["noprov", "fsatrace"]
    ],
    "fast": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in ["noprov", "strace", "fsatrace", "reprozip"]
    ],
    "finished": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in ["noprov", "strace", "fsatrace", "rr", "reprozip"]
        # ltrace
    ],
    "working-ltrace": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in ["noprov", "strace", "fsatrace", "rr", "reprozip", "sciunit", "ptu", "care", "ltrace"]
    ],
    "old-working": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in ["noprov", "strace", "fsatrace", "reprozip"]
    ],
    "new-working": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in ["sciunit", "care"]
    ],
    "working": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in ["noprov", "strace", "fsatrace", "rr", "reprozip", "care"]
    ],
}
