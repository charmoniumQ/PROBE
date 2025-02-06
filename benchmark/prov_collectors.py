import dataclasses
import warnings
import subprocess
import os
import yaml
import re
from collections.abc import Mapping
import pathlib
from util import check_returncode, flatten1
from typing import Callable, cast, Any
from compound_pattern import CompoundPattern
import util
import command
from workloads import nix_path, cmd, nix, var, combine


PATH_SIZE = 4096
prov_dir = var("prov_dir")
prov_log = combine(var("prov_dir"), "/log")
work_dir = var("work_dir")
env = nix_path(".#coreutils", "/bin/env")
common_parent = var("common_parent")


@dataclasses.dataclass(frozen=True)
class ProvOperation:
    type: str
    target0: pathlib.Path | None
    target1: pathlib.Path | None
    args: object | None


class ProvCollector:
    @property
    def name(self) -> str:
        return self.__class__.__name__.lower()
    timeout_multiplier: float = 10
    requires_empty_dir: bool
    run_cmd: command.Command = cmd()
    setup_cmd: command.Command = cmd()
    teardown_cmd: command.Command = cmd()

    def count(self, prov_dir: pathlib.Path, exe: pathlib.Path) -> tuple[ProvOperation, ...]:
        return ()


class NoProv(ProvCollector):
    timeout_multiplier = 1


class AbstractTracer(ProvCollector):
    line_pattern: CompoundPattern
    group_processors: Mapping[str, Callable[[str], object]] = {}
    use_get_dlib_on_exe: bool

    def _filter_op(self, op: ProvOperation) -> list[ProvOperation]:
        return [op]

    def count(self, prov_dir: pathlib.Path, exe: pathlib.Path) -> tuple[ProvOperation, ...]:
        log_contents = (prov_dir / "log").read_text()
        operations = []
        def identity(obj):
            return obj
        if self.use_get_dlib_on_exe and is_executable_or_library(pathlib.Path(exe)):
            for lib in get_dlibs(exe):
                operations.append(ProvOperation("dldep", pathlib.Path(lib), None, {"source": exe}))
        for line in log_contents.split("\n"):
            if line.strip():
                line = line.strip()
                if (match := self.line_pattern.match(line)):
                    args = match.combined_groupdict()
                    op = args.get("op")
                    if op is not None:
                        operations.extend(self._filter_op(ProvOperation(
                            op,
                            pathlib.Path(util.expect_type(str, args.get("target0"))) if args.get("target0") else None,
                            pathlib.Path(util.expect_type(str, args.get("target1"))) if args.get("target1") else None,
                            {
                                key: self.group_processors.get(key, identity)(val)
                                for key, val in args.items()
                                if key not in {"target0", "target1", "op"}
                            },
                        )))
                else:
                    warnings.warn("Unable to parse line: " + line)
        return tuple(operations)


function_name = "[a-z0-9_.]+"

strace_syscalls = [
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
    "fcntl",

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
]

class STrace(AbstractTracer):
    timeout_multiplier = 3

    run_cmd = cmd(
        nix_path(".#strace", "/bin/strace"),
        "--follow-forks",
        "--trace",
        ",".join(strace_syscalls),
        "--output",
        prov_log,
        "-s",
        str(PATH_SIZE),
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



ldd_regex = re.compile(r"\s+(?P<path>/[a-zA-Z0-9./-]+)\s+\(")

def _get_dlibs(exe_or_dlib: pathlib.Path, found: set[pathlib.Path]) -> None:
    env: Mapping[str, str] = {}
    proc = subprocess.run(
        [
            nix_path(".#glibc_multi_bin", "/bin/ldd").expand({}),
            exe_or_dlib,
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    check_returncode(proc, env)
    for match in ldd_regex.finditer(proc.stdout):
        path = match.group("path")
        if path is not None and path not in found:
            found.add(pathlib.Path(path))
            _get_dlibs(exe_or_dlib, found)


def get_dlibs(exe_or_dlib: pathlib.Path) -> set[pathlib.Path]:
    ret = set[pathlib.Path]()
    _get_dlibs(exe_or_dlib, ret)
    return ret


ltrace_libcalls = [
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
]


class LTrace(AbstractTracer):
    timeout_multiplier = 10

    run_cmd = cmd(
        nix_path(".#ltrace", "/bin/ltrace"),
        "-f",
        "--config",
        nix(".#ltrace-conf"),
        "-L",
        "-x",
        "-*+" + "+".join(ltrace_libcalls),
        "--output",
        prov_log,
        "-s",
        str(PATH_SIZE),
        "--",
        # $ ltrace ./script.sh
        # "./script.sh" is not an ELF file
        nix_path(".#coreutils", "/bin/env"),
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
                op.target0 is not None and is_executable_or_library(pathlib.Path(op.target0)),
        ]):
            # For dlopen calls, we need to add the files dlopen(op.target0) will call
            return [
                op,
                *(
                    ProvOperation(type="dload_dep", target0=dlib, target1=None, args=None)
                    for dlib in (get_dlibs(op.target0) if op.target0 is not None else [])
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


PATH_MAX = os.pathconf('/', 'PC_PATH_MAX')
NAME_MAX = os.pathconf('/', 'PC_NAME_MAX')


def is_executable_or_library(path: pathlib.Path) -> bool:
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
    timeout_multiplier = 2
    line_pattern = CompoundPattern(re.compile(r"^(?P<op>.)\|(?P<target0>[^|]*)(?:\|(?P<target1>.*))?$"))
    use_get_dlib_on_exe = True

    run_cmd = cmd(
        nix_path(".#fsatrace", "/bin/fsatrace"),
        "rwmdqt",
        prov_log,
        "--",
    )

    def _filter_op(self, op: ProvOperation) -> list[ProvOperation]:
        operations = [op]
        if op.type == "r" and op.target0 is not None and is_executable_or_library(op.target0):
            for dlib in get_dlibs(op.target0):
                operations.append(ProvOperation("l", dlib, None, None))
        return operations


class PTU(ProvCollector):
    timeout_multiplier = 10
    run_cmd = cmd(
        nix_path(".#provenance-to-use", "/bin/ptu"),
        "-o",
        prov_dir,
    )

    def count(self, prov_dir: pathlib.Path, exe: pathlib.Path) -> tuple[ProvOperation, ...]:
        root = prov_dir / "cde-root"
        return tuple(
            ProvOperation("read", file.relative_to(root), None, None)
            for file in root.glob("**")
        )


class CDE(ProvCollector):
    timeout_multiplier = 10
    run_cmd = cmd(
        nix_path(".#cde", "/bin/cde"),
        "-o",
        prov_dir,
    )

    def count(self, prov_dir: pathlib.Path, exe: pathlib.Path) -> tuple[ProvOperation, ...]:
        root = prov_dir / "cde-root"
        return tuple(
            ProvOperation("read", file.relative_to(root), None, None)
            for file in root.glob("**")
        )


class RR(ProvCollector):
    timeout_multiplier = 5

    run_cmd = cmd(
        env,
        combine("_RR_TRACE_DIR=", prov_dir),
        nix_path(".#rr", "/bin/rr"),
        "record",
    )

    teardown_cmd = cmd(
        nix_path(".#rr", "/bin/rr"),
        "pack",
        combine(prov_dir, "/latest-trace"),
    )


class ReproZip(ProvCollector):
    timeout_multiplier = 5
    setup_cmd = cmd(
        nix_path(".#reprozip", "/bin/reprozip"),
        "usage_report",
        "--disable",
    )

    run_cmd = cmd(
        nix_path(".#reprozip", "/bin/reprozip"),
        "trace",
        "--dir",
        prov_log,
    )

    def count(self, prov_dir: pathlib.Path, exe: pathlib.Path) -> tuple[ProvOperation, ...]:
        config = yaml.safe_load((prov_dir / "log" / "config.yml").read_text())
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
    timeout_multiplier = 10
    setup_cmd = cmd(
        env,
        combine("SCIUNIT_HOME=", prov_dir),
        nix_path(".#sciunit2", "/bin/sciunit"),
        "create",
        "-f",
        "test",
    )

    run_cmd = cmd(
        nix_path(".#sciunit2", "/bin/sciunit"),
        "exec",
    )


# class Darshan(ProvCollector):


# class BPFTrace(ProvCollector):


# class SpadeFuse(ProvCollector):
#     # echo -e "add reporter LinuxFUSE $PWD/test2\nadd storage Neo4j database=$PWD/spade.graph" | ./result/bin/spade control
#     # echo -e "remove reporter LinuxFUSE\nremove storage Neo4j" | ./result/bin/spade control
#     _start = "\n".join([
#         "add reporter LinuxFUSE {workdir}",
#         "add storage Neo4j database={log}/spade.graph",
#         "add analyzer CommandLine",
#     ])
#     _stop = "\n".join([
#         "remove reporter LinuxFUSE",
#         "remove storage Neo4j",
#     ])
#     _query = "\n".join([
#         "export > {log}/galileo.dot",
#         "dump all",
#     ])

    # def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
    #     self._workdir = workdir
    #     # SPADE FUSE must start in a non-existant directory
    #     self._workdir.unlink()
    #     assert not self._workdir.exists()
    #     subprocess.run(
    #         ["spade", "start"],
    #         check=True,
    #         capture_output=True,
    #         env=env,
    #     )

    # def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
    #     assert self._workdir is not None
    #     subprocess.run(
    #         ["spade", "control"],
    #         check=True,
    #         capture_output=True,
    #         text=True,
    #         input=self._start.format(workdir=self._workdir, log=log),
    #     )
    #     return (
    #         "env", "--chdir", self._workdir, *cmd
    #     )

    # def stop(self, env: Mapping[str, str]) -> None:
    #     subprocess.run(
    #         ["spade", "control"],
    #         check=True,
    #         capture_output=True,
    #         text=True,
    #         input=self._stop.format(),
    #         env=env,
    #     )


# class SpadeAuditd(ProvCollector):

#     def start(self, log: Path, size: int, workdir: Path, env: Mapping[str, str]) -> None:
#         # https://github.com/ashish-gehani/SPADE/blob/b24daa56332e8478711bee80e5ac1f1558ff5e52/src/spade/reporter/audit/AuditControlManager.java#L57
#         syscalls = ("fileIO=false", "netIO=true", "IPC=true")
#         subprocess.run(["spade", "start"], check=True, capture_output=True, env=env)
#         subprocess.run(["spade", "control", "add", "reporter", "Audit", *syscalls], check=True, capture_output=True, env=env)

#     def stop(self, env: Mapping[str, str]) -> None:
#         subprocess.run(
#             ["spade", "stop"],
#             check=True,
#             capture_output=True,
#             env=env,
#         )


class LinuxAudit(ProvCollector):
    timeout_multiplier = 1
    run_cmd = cmd(
        str(project_root / "benchmark_utils/audit"),
        prov_log,
        combine("--directories=/nix/store/,", work_dir),
    )


class Care(ProvCollector):
    timeout_multiplier = 5
    run_cmd = cmd(
        nix_path(".#care", "/bin/care"),
        combine("--output=", prov_dir, "/log.tar.xz"),
        "--revealed-path=/tmp",
        "--revealed-path=" + str(pathlib.Path.home()),
        "--verbose=-1",
    )

    # def count(self, pr: pathlib.Path, exe: pathlib.Path) -> tuple[ProvOperation, ...]:
    #     prefix = "main/rootfs"
    #     with tarfile.open(name=log, mode='r') as tar_obj:
    #         return tuple(
    #             ProvOperation("use", pathlib.Path(member.name[len(prefix):]), None, None)
    #             for member in tar_obj.getmembers()
    #             if member.name.startswith(prefix)
    #         )


class Probe(ProvCollector):
    timeout_multiplier = 1.5
    run_cmd = cmd(
        nix_path("..#probe-bundled", "/bin/probe"),
        "record",
        "--no-transcribe",
        "--output",
        prov_log,
    )

    # def count(self, log: pathlib.Path, exe: pathlib.Path) -> tuple[ProvOperation, ...]:
    #     subprocess.run(
    #         [
    #             nix_path("..#probe-bundled", "/bin/probe").expand(),
    #             "transcribe",
    #             "--input",
    #             str(log),
    #             str(log.parent / "prov2"),
    #         ],
    #         check=True,
    #         text=True,
    #         capture_output=True,
    #     )
    #     ops = list(map(json.loads, subprocess.run(
    #         [
    #             nix_path("..#probe-bundled", "/bin/probe").expand(),
    #             "export",
    #             "ops-jsonl",
    #             str(log.parent / "prov2"),
    #         ],
    #         check=True,
    #         text=True,
    #         capture_output=True,
    #     ).stdout.split("\n")))
    #     return tuple(
    #         ProvOperation(op["op_data_type"], None, None, None)
    #         for op in ops
    #     )


class ProbeCopyEager(Probe):
    timeout_multiplier = 3
    run_cmd = cmd(
        nix_path("..#probe-bundled", "/bin/probe"),
        "record",
        "--copy-files-eagerly",
        "--no-transcribe",
        "--output",
        prov_log,
    )


class ProbeCopyLazy(Probe):
    timeout_multiplier = 3
    run_cmd = cmd(
        nix_path("..#probe-bundled", "/bin/probe"),
        "record",
        "--copy-files-lazily",
        "--no-transcribe",
        "--output",
        prov_log,
    )


class NoProvStable(NoProv):
    run_cmd = cmd(
        nix_path(".#util-linux", "/bin/setarch"),
        "--addr-no-randomize",
        nix_path(".#libfaketime", "/bin/faketime"),
        "2025-01-01 00:00:00",
    )


podman_img = "debian:bookworm-20250113-slim"
podman = shutil.which("podman")
class Podman(NoProv):
    setup_cmd = cmd(
        podman,
        "image",
        "pull",
        podman_img,
    )
    run_cmd = cmd(
        podman,
        "run",
        combine("--volume=", work_dir, ":", work_dir),
        "--volume=/nix/store:/nix/store:ro",
        "--rm",
        podman_img,
    )


class Bubblewrap(NoProv):
    run_cmd = cmd(
        nix_path(".#bubblewrap", "/bin/bwrap"),
        "--unshare-pid",
        "--unshare-net",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--ro-bind", "/nix/store", "/nix/store",
        "--bind", work_dir, work_dir,
    )


PROV_COLLECTORS: list[ProvCollector] = [
    NoProv(),
    STrace(),
    LTrace(),
    # FSATrace(),
    CDE(),
    RR(),
    ReproZip(),
    Sciunit(),
    Care(),
    PTU(),
    Probe(),
    ProbeCopyEager(),
    ProbeCopyLazy(),
    RustAuditWrapper(),
    # SpadeFuse(),
    # SpadeAuditd(),
    # Darshan(),
    # BPFTrace(),
    NoProvStable(),
    Podman(),
    # Podman requires newuidmap to be on the $PATH and have setuid.
    # Nix can put newuidmap on the path, but it can't do setuid for you.
    Bubblewrap(),
]

PROV_COLLECTOR_GROUPS: Mapping[str, list[ProvCollector]] = {
    # Singleton groups
    **{
        prov_collector.name: [prov_collector]
        for prov_collector in PROV_COLLECTORS
    },
    "all": PROV_COLLECTORS,
    "fast": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name not in ["ltrace"]
    ],
    "run-for-usenix": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        # sciunit has error due to our invocation
        # rr doesn't work unless tracing is enabled
        # cde is similar to ptu
        if prov_collector.name in ["noprov", "strace", "care", "probe", "ptu", "probecopylazy", "rr"]
    ],
    "probes": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name.startswith("probe")
    ],
    "noprovs": [
        prov_collector
        for prov_collector in PROV_COLLECTORS
        if prov_collector.name in {"noprov", "noprovstable", "podman", "bubblewrap"}
    ],
}
