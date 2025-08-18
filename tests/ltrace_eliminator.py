import shlex
import collections
import subprocess
import pathlib
import sys
project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(
    0,
    str(project_root / "benchmark")
)
from compound_pattern import ltrace_pattern # type: ignore # noqa: E402

log_file = pathlib.Path("ltrace.log")

#
ltrace_command = [
    "ltrace",
    "-A5",
    "-f",
    "--indent=2",
    "-s4096",
    "-S"
    "-o",
    str(log_file),
    "-L",
    "-x",
]

command: list[str] = [
    "diff", "test_file.txt", "test_file.txt"
]


excluded_functions = [
    "*.constprop.0",
    "*.isra.0",
    "*.localalias"
    "*.part.0",
    "*_builtin",
    "*_dollar_*",
    "*_frame",
    "*_internal",
    "*_langinfo*",
    "*_list",
    "*_module",
    "*_parser_*"
    "*_stream",
    "*_variable*",
    "*_word",
    "*_word_*",
    "*_words",
    "*alloc",
    "*array*",
    "*command*",
    "*flush*",
    "*free",
    "*getc",
    "*getenv",
    "*pipestatus*",
    "*printf*",
    "*shell*",
    "*textdomain",
    "*write",
    "_*",
    "add_alias2.part.0",
    "alias_*",
    "alloc_perturb",
    "bfd_*",
    "bind_lastarg",
    "brace_*"
    "brk",
    "cfree",
    "check_dev_tty",
    "execute_connection",
    "fgets*"
    "frame_dummy",
    "getdelim",
    "getenv",
    "getpagesize",
    "hash_*",
    "htab_*",
    "itos",
    "list_*",
    "malloc_*",
    "mbs*",
    "mem*",
    "new_composite_name",
    "notify_and_cleanup",
    "param_*",
    "parse_*",
    "procsub_*",
    "pthread_*",
    "sbrk",
    "sigadd*",
    "sigemptyset*",
    "str*",
    "sysconf",
    "tfind",
    "tsearch",
    "var_lookup",
    "word_*",
    "xtrace_init",
    "yyparse",
]

included_functions = [
    "access",
    "fstatat",
    "fstat",
    "stat",
    "readdir",
    "fopen",
    "setlocale",
    "fclose",
    "opendir",
    "opendir_tail",
    "open",
    "close",
    "mmap",
    "close",
    "open",
]

timeout = 5


continue_ltracing = True
while continue_ltracing:
    ltrace_selector = "*+@libc.so.6-" + "-".join(excluded_functions)
    composed_command = [*ltrace_command, ltrace_selector, *command]
    print(shlex.join(composed_command))
    try:
        proc = subprocess.run(
            composed_command,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"Timeout of {timeout} expired")
    else:
        print(f"Process exited {proc.returncode}")
    function_calls = collections.Counter[tuple[str, str]]()
    lines = 0
    functions = 0
    with log_file.open() as log_file_obj:
        for line in log_file_obj:
            lines += 1
            line = line.strip()
            if match := ltrace_pattern.match(line):
                if fname := match.combined_groupdict().get("op"):
                    functions += 1
                    lib = match.combined_groupdict().get("lib")
                    function_calls[(fname, lib)] += 1
            else:
                print("Failed to match", line)
                ltrace_pattern.match(line, verbose=True)
    print("N lines", lines)
    print("N funcitons", functions)
    print("N unique functions", len(function_calls))
    if not function_calls:
        break
    for (function_call, lib), count in function_calls.most_common(50):
        print(count, function_call, lib)
        if function_call not in included_functions:
            match input("> "):
                case "exclude":
                    excluded_functions.append(function_call)
                    print(excluded_functions)
                case "exclude*":
                    excluded_functions.append(input())
                    print(excluded_functions)
                case "include":
                    included_functions.append(function_call)
                    print(included_functions)
                case "run":
                    continue_function_call_elimination = False
                    break
                case "timeout":
                    print(timeout)
                    timeout_str = input(timeout)
                    try:
                        timeout = int(timeout_str)
                    except Exception as exc:
                        print(exc)
                case "quit":
                    continue_ltracing = False
                    print("excluded:", excluded_functions)
                    print("included:", included_functions)
                    print("command:", command)
                    print("timeout:", timeout)
                    print("shlex.join(composed_command):", shlex.join(composed_command))
                    break
                case _:
                    print("What?")
