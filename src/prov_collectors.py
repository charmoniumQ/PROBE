import shutil
import subprocess
import re
from collections import Counter
from collections.abc import Sequence, Mapping
from pathlib import Path
from util import run_all, terminate_or_kill, CmdArg


result_bin = Path(__file__).resolve().parent / "result/bin"
result_lib = result_bin.parent / "lib"


class ProvData:
    pass


class ProvCollector:
    @property
    def requires_empty_dir(self) -> bool:
        return False

    def start(self, log: Path, size: int, workdir: Path) -> None | Sequence[CmdArg]:
        return None

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return cmd

    def stop(self, proc: None | subprocess.Popen[bytes]) -> None:
        if proc:
            terminate_or_kill(proc, 10)

    def __str__(self) -> str:
        return self.name

    def count(self, log: Path) -> tuple[Counter[str], frozenset[str]]:
        return Counter[str](), frozenset[str]()

    @property
    def name(self) -> str:
        return self.__class__.__name__.lower()

    @property
    def method(self) -> str:
        return "None"

    @property
    def submethod(self) -> str:
        return "None"


class NoProv(ProvCollector):
    name = "no prov"

libcalls = "+".join([
    # File syscalls
    "open*", "fopen*", "creat*", "fstat*", "lstat*", "fchdir",
    "chdir", "chmod", "fchmod*", "lchmod", "chown", "fchown*",
    "lchown", "access", "eaccess", "faccessat", "euidaccess" "mknod*",
    "mkfifo*", "mkdir*", "rename*", "symlink*", "unlink*", "rmdir",

    # File finegrain syscalls
    # "read*", "write*", "getdents*", "mmap*", "e?poll*", "*select*",
    # "fadvise*", "f?sync*", "lseek", "ioctl", "fcntl*", "flock", "flockfile"

    # xattr syscalls
    "fgetxattr", "lgetxattr", "getxattr",
    "fsetxattr", "lsetxattr", "setxattr"
    "flistxattr", "llistxattr", "listxattr"
    "fremovexattr", "lremovexattr", "removexattr",

    # FD syscalls
    "close*", "fclose*", "dup*",

    # Socket syscalls
    "bind", "accept*", "connect", "send*", "recv*", "shutdown"

    # Proc syscalls
    "clone", "fork", "vfork", "exec*", "fexec*", "exit", "chroot",
])

syscalls = ",".join([
    # File syscalls "open", "openat", "openat2",
    "creat", "fstat", "newfstatat", "chmod", "fchmod", "fchmodat",
    "chown", "fchown", "lchown", "fchownat", "access", "faccessat",
    "mknod", "mknodat", "mkdir", "mkdirat", "rename", "renameat",
    "symlink", "symlinkat", "unlink", "unlinkat", "rmdir",

    # File finegrain syscalls
    # "read*", "write*", "getdents*", "mmap*", "e?poll*", "*select*",
    # "fadvise*", "f?sync*", "lseek", , "fcntl", "ioctl", "flock", 
    
    # xattr syscalls
    "fgetxattr", "flistxattr", "fremovexattr", "fsetxattr",
    "getxattr", "lgetxattr", "listxattr", "llistxattr",
    "lremovexattr", "lsetxattr", "removexattr", "setxattr",
    
    # FD syscalls
    "close", "close_range", "dup", "dup2", "dup3",
    
    # Socket syscalls
    "bind", "accept", "accept4", "connect", "socketcall", "shutdown",

    # Socket fine-grain syscalls
    "send", "sendfile", "sendfile64", "sendmsg", "sendmmsg", "sendto",
    "recv", "recvfrom", "recvmsg", "recvmmsg",
    
    # Proc syscalls
    "clone", "clone3", "fork", "vfork", "execve", "execveat", "exit",
    "exit_group", "chroot", "fchdir", "chdir",
])


class STrace(ProvCollector):
    method = "tracing"
    submethod = "syscalls"

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return (
            "./result/bin/strace", "--follow-forks", "--trace",
            syscalls, "--output", log, "-s", f"{size}", *cmd,
        )

    def count(self, log: Path) -> tuple[Counter[str], frozenset[str]]:
        log_contents = log.read_text()
        # Log line example:
        # 5     execve("/home/sam/box/prov/src/result/bin/python", ...) = 0
        calls_pattern = re.compile(r"^\d+ +([a-z0-9]+)\(", flags=re.MULTILINE)
        calls = Counter[str]()
        for match in calls_pattern.finditer(log_contents):
            calls[match.group(1)] += 1
        files_pattern = re.compile(r"\"(.+?)\"")
        files = set()
        for match in files_pattern.finditer(log_contents):
            files.add(match.group(1))
        return calls, frozenset(files)


class LTrace(ProvCollector):
    method = "tracing"
    submethod = "libc calls"

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return (
            "./result/bin/ltrace", "-f", "-e", f"{libcalls}",
            f"--output", log, "-s", f"{size}", "--", *cmd,
        )

    def count(self, log: Path) -> tuple[Counter[str], frozenset[str]]:
        log_contents = log.read_text()
        # Log line example:
        # [pid 727228] libpython3.11.so.1.0->open64("path/to//numpy/ma/extras.py", 524288, 0666) = 3
        calls_pattern = re.compile(r"^\[pid \d+\] [^-]*?->([a-z0-9]+)\(", flags=re.MULTILINE)
        calls = Counter[str]()
        for match in calls_pattern.finditer(log_contents):
            calls[match.group(1)] += 1
        files_pattern = re.compile("\"(.+?)\"")
        files = set()
        for match in files_pattern.finditer(log_contents):
            files.add(match.group(1))
        return calls, frozenset(files)


class FSATrace(ProvCollector):
    method = "lib instrm."
    submethod = "libc I/O"
    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return ("./result/bin/fsatrace", "rwmdq", log, "--", *cmd)

    def count(self, log: Path) -> tuple[Counter[str], frozenset[str]]:
        log_contents = log.read_text()
        pattern = re.compile(r"^(.)|(.*?)$", flags=re.MULTILINE)
        calls = Counter[str]()
        files = set()
        for match in pattern.finditer(log_contents):
            calls[match.group(1)] += 1
            files.add(match.group(2))
        return calls, frozenset(files)


class Darshan(ProvCollector):
    method = "lib instrm."
    submethod = "libc I/O"

    def run(self, cmd: Sequence[CmdArg], log: Path, size: int) -> Sequence[CmdArg]:
        return (
            result_bin / "env", f"DARSHAN_LOG_PATH={log.parent}",
            "DARSHAN_MOD_ENABLE=DXT_POSIX", "DARSHAN_ENABLE_NONMPI=1",
            f"LD_PRELOAD={result_lib}/libdarshan.so", *cmd,
        )


class BPFTrace(ProvCollector):
    method = "auditing"
    submethod = "eBPF"

    def __init__(self) -> None:
        self.bpfscript = Path("prov.bt").read_text()
        raise NotImplementedError("Need to actually write script")

    def start(self, log: Path, size: int, workdir: Path) -> None | Sequence[CmdArg]:
        return (
            result_bin / "env", f"BPFTRACE_STRLEN={size}", result_bin
            / "bpftrace", "-B", "full", "-f", "json", "-o", log, "-e",
            self.bpfscript,
        )


class SpadeFuse(ProvCollector):
    requires_empty_dir = True
    method = "FS instrm."
    submethod = "FUSE"
    name = "SPADE+FUSE"

    def start(self, log: Path, size: int, workdir: Path) -> None | Sequence[CmdArg]:
        return run_all(
            (result_bin / "spade", "start"),
            (result_bin / "spade", "control", "add", "reporter", "LinuxFUSE", f"{workdir}"),
        )


class SpadeAuditd(ProvCollector):
    method = "auditing"
    submethod = "auditd"
    name = "SPADE+Auditd"

    def start(self, log: Path, size: int, workdir: Path) -> None | Sequence[CmdArg]:
        # https://github.com/ashish-gehani/SPADE/blob/b24daa56332e8478711bee80e5ac1f1558ff5e52/src/spade/reporter/audit/AuditControlManager.java#L57
        syscalls = ("fileIO=false", "netIO=true", "IPC=true")
        return run_all(
            (result_bin / "spade", "start"),
            (result_bin / "spade", "control", "add", "reporter", "Audit", *syscalls),
        )


class Auditd(ProvCollector):
    method = "auditing"
    submethod = "auditd"

    def start(self, log: Path, size: int, workdir: Path) -> None | Sequence[CmdArg]:
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
                (result_bin / "auditctl", "-D"),
                (result_bin / "auditctl", *auditctl_rules),
            ),
            check=True,
        )

    def stop(self, proc: None | subprocess.Popen[bytes]) -> None:
        subprocess.run([result_bin / "auditctl", "-D"], check=True)


baseline = NoProv()


PROV_COLLECTORS: Sequence[ProvCollector] = (
    baseline,
    STrace(),
    LTrace(),
    FSATrace(),
    Darshan(),
    # BPFTrace(),
    # SpadeFuse(),
    # SpadeAuditd(),
    # Auditd(),
)
