import collections
import dataclasses
import datetime
import fnmatch
import pathlib
import re
import shlex
import subprocess


@dataclasses.dataclass
class Symbol:
    name: str
    library: str | None

@dataclasses.dataclass
class AtomicFunctionCall:
    symbol: Symbol
    args: str
    ret: str

@dataclasses.dataclass
class UnfinishedFunctionCall:
    symbol: Symbol
    args: str

@dataclasses.dataclass
class FunctionReturn:
    symbol: Symbol
    args: str | None
    ret: str | None
    call: UnfinishedFunctionCall | None

@dataclasses.dataclass
class NoReturn:
    symbol: Symbol
    ret: str

@dataclasses.dataclass
class TransferCall:
    call: str

@dataclasses.dataclass
class Exit:
    status: int

@dataclasses.dataclass
class Signal:
    signal: str
    description: str

@dataclasses.dataclass
class State:
    stack: collections.abc.Mapping[int, list[UnfinishedFunctionCall]] = dataclasses.field(
        default_factory=lambda: collections.defaultdict(list)
    )


Event = UnfinishedFunctionCall | AtomicFunctionCall | FunctionReturn | NoReturn | TransferCall | Signal | Exit


def parse(
        log: collections.abc.Iterable[str],
) -> collections.abc.Iterator[tuple[State, int, Event]]:
    state = State()
    lineno = 0
    for line in log:
        lineno += 1
        line = line.strip()
        pid_match = re.match(r"(\d+) ( *)(.*)$", line)
        if pid_match:
            pid = int(pid_match.group(1))
            stack = state.stack[pid]
            #indentation = len(pid_match.group(2))
            line = pid_match.group(3)
            if symbol_match := re.match(r"([a-zA-Z0-9._-]+)(@[a-zA-Z0-9._-]*)?\((.*)$", line):
                symbol = Symbol(
                    symbol_match.group(1),
                    symbol_match.group(2)[1:] if symbol_match.group(2) else None,
                )
                line = symbol_match.group(3)
                if atomic_function_call_match := re.match(r"(.*)\) += (.*)$", line):
                    yield state, pid, AtomicFunctionCall(
                        symbol,
                        atomic_function_call_match.group(1),
                        atomic_function_call_match.group(2),
                    )
                elif unfinished_function_call_match := re.match(r"(.*) <unfinished \.\.\.>$", line):
                    unfinished_function_call = UnfinishedFunctionCall(
                        symbol,
                        unfinished_function_call_match.group(1),
                    )
                    stack.append(unfinished_function_call)
                    yield state, pid, unfinished_function_call
                elif noreturn_call_match := re.match(r"(.*) <no return \.\.\.>$", line):
                    stack.clear()
                    noreturn = NoReturn(
                        symbol,
                        noreturn_call_match.group(1),
                    )
                    stack.clear()
                    yield state, pid, noreturn
                else:
                    raise RuntimeError(f"Line {lineno}: Could not parse:\n{line!r}")
            elif exited_match := re.match(r"\+\+\+ exited \(status (\d+)\) \+\+\+$", line):
                yield state, pid, Exit(int(exited_match.group(1)))
            elif function_return_match := re.match(r"<\.\.\. (.*) resumed> (.+)?\) +=(?: (.*))?$", line):
                #name = function_return_match.group(1)
                args = function_return_match.group(2)
                ret = function_return_match.group(3)
                if stack:
                    call = stack.pop()
                else:
                    call = None
                #assert call.symbol.name == name, (call.symbol.name, name)
                yield state, pid, FunctionReturn(symbol, args, ret, call)
            elif transfer_call_match := re.match("--- Called (.*) ---$", line):
                stack.clear()
                yield state, pid, TransferCall(transfer_call_match.group(1))
            elif transfer_call_match := re.match("--- (SIG[A-Z12]*) (.*) ---$", line):
                stack.clear()
                yield state, pid, Signal(transfer_call_match.group(1), transfer_call_match.group(1))
            else:
                raise RuntimeError(f"Line {lineno}: Could not parse:\n{line!r}")
        else:
            raise RuntimeError(f"Line {lineno}: Could not parse:\n{line!r}")


def run_ltrace(
        cmd: list[str],
        exclude: list[str],
        timeout: float,
) -> tuple[bool, int, list[tuple[State, int, Event]]]:
    exclude_flag = "*@SYS+*@libc.so.6" + ("-" if exclude else "") + "-".join(exclude)
    tmpfile = pathlib.Path("ltrace.log")
    real_cmd = ["ltrace", "-A5", "-f", "--indent=1", "-s4096", "-S", "-L", "-x", exclude_flag, "--output", str(tmpfile), *cmd]
    print(shlex.join(real_cmd))
    try:
        proc = subprocess.run(
            real_cmd,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        with tmpfile.open() as tmpfile_obj:
            return (True, 0, list(parse(tmpfile_obj)))
    else:
        with tmpfile.open() as tmpfile_obj:
            return (False, proc.returncode, list(parse(tmpfile_obj)))


if __name__ == "__main__":
    command: list[str] = [
        "bash",
        "-c",
        '../../../examples/echo.exe hi > test_file && ../../../examples/cat.exe test_file > test_file2',
    ]

    timeout = 5
    excluded_functions = [
        # Libc internals
        #"_*@libc.so.6", # not this, __openat_2 would be matched!
        "__str*@libc.so.6",
        "__mem*@libc.so.6",
        "__pthread*@libc.so.6",
        "___pthread*@libc.so.6",
        "__GI_*@libc.so.6",
        "_IO_*@libc.so.6",
        "__cxa_*@libc.so.6",
        "__wctob@libc.so.6",
        "__btowc@libc.so.6",
        "__free@libc.so.6",
        "__gconv*@libc.so.6",
        "__getdelim*@libc.so.6",
        "__tsearch*@libc.so.6",
        "__tfind*@libc.so.6",


        # Libc stuff we don't care about
        "wctob@libc.so.6",
        "bcmp@libc.so.6",
        "btowc@libc.so.6",
        "wctype*@libc.so.6",
        "*textdomain@libc.so.6",
        "alloc_*@libc.so.6",
        "sysconf@libc.so.6",
        "getpagesize@libc.so.6",
        "str*@libc.so.6",
        "*strto*@libc.so.6",
        "mb*@libc.so.6",
        "mem*@libc.so.6",
        "*_module@libc.so.6",
        "*alias2@libc.so.6",
        "*alloc@libc.so.6",
        "*fput*@libc.so.6",
        "*fget*@libc.so.6",
        "*flush*@libc.so.6",
        "free@libc.so.6",
        "*free@libc.so.6",
        "*printf*@libc.so.6",
        "qsort*@libc.so.6",
        "alias*@libc.so.6",
        "tfind@libc.so.6",
        "tsearch@libc.so.6",
        "pthread_*@libc.so.6",
        "sig*@libc.so.6",
        "?etdelim@libc.so.6",
        "*locale@libc.so.6",
        "sem_*@libc.so.6",
        "index@libc.so.6",

        # Ignore libc and syscalls
        "rt_sig*@*",
        "brk@*",
        "sbrk@*",
        "mprotect@*",
        "*prctl@*",
        "read*@*",
        "write*@*",
        "pread*@*",
        "pwrite*@*",
        "prlimit*@*",
        "rlimit*@*",
        "ioctl*@*",
        "futex*@*",
        "restart_syscall@SYS",
        "getc@*",
        "putc@*",
        "clock_gettime@*",

        # These look like GCC leftovers?
        "*.constprop.*",
        "*.isra.*",
        "*.part.*",
        "*.localalias.*",
    ]
    included_functions = [
        "getenv@*",
        "*access@*",
        "*accessat@*",
        "*stat@*",
        "*statat@*",
        "*open@*",
        "*openat@*",
        "*close@*",
        "*seek@*",
        "mmap@*",
        "munmap@*",
        "getenv@libc.so.6",
    ]

    continue_ltracing = True
    while continue_ltracing:
        start = datetime.datetime.now()
        timeout, returncode, events = run_ltrace(command, excluded_functions, timeout)
        end = datetime.datetime.now()
        if timeout:
            print("Timeout reached")
        else:
            print(f"Process exited status {returncode} in {(end - start).total_seconds():.1f}seconds")

        function_calls = collections.Counter[tuple[str, str | None]]()
        n_events = 0
        for _state, _pid, event in events:
            n_events += 1
            if isinstance(event, AtomicFunctionCall | UnfinishedFunctionCall):
                function_calls[(event.symbol.name, event.symbol.library)] += 1
        print("N lines", n_events)
        print("N unique functions", len(function_calls))

        if not function_calls:
            break

        in_function_list = True
        for (function_call, lib), count in function_calls.most_common(50):
            tag = function_call + ("@" + lib if lib else "")
            including = any(
                fnmatch.fnmatch(tag, included_function)
                for included_function in included_functions
            )
            excluding = any(
                fnmatch.fnmatch(tag, excluded_function)
                for excluded_function in excluded_functions
            )
            print(count, tag, f"{including=}", f"{excluding=}")
            if not including and not excluding:
                in_function_selection = True
                while in_function_selection:
                    match input("> "):
                        case "exclude":
                            excluded_functions.append(tag)
                            in_function_selection = False
                        case "exclude*":
                            excluded_functions.append(input())
                            in_function_selection = False
                        case "include":
                            included_functions.append(tag)
                            in_function_selection = False
                        case "include*":
                            included_functions.append(input())
                            in_function_selection = False
                        case "run":
                            in_function_selection = False
                            in_function_list = False
                            continue_function_call_elimination = False
                        case "timeout":
                            print(timeout)
                            timeout_str = input(timeout)
                            try:
                                timeout = int(timeout_str)
                            except Exception as exc:
                                print(exc)
                        case "quit":
                            in_function_selection = False
                            in_function_list = False
                            continue_ltracing = False
                            print("excluded:", excluded_functions)
                            print("included:", included_functions)
                            print("command:", command)
                            print("timeout:", timeout)
                        case _:
                            print("What?")
                if not in_function_list:
                    break
