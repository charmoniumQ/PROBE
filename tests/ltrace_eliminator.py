import shlex
import collections
import subprocess
import pathlib
project_root = pathlib.Path(__file__).resolve().parent.parent
import sys
sys.path.insert(
    0,
    str(project_root / "benchmark")
)
from compound_pattern import ltrace_pattern

log_file = pathlib.Path("ltrace.log")

ltrace_command = [
    "ltrace",
    "-f",
    "-F",
    f"{project_root}/benchmark/ltrace.conf",
    "-s",
    "4096",
    "-o",
    str(log_file),
    "-L",
    "-x",
]

command: list[str] = [
    "bash", "-c", "gcc -c test.c"
]


excluded_functions = [
    "_*",
    "*alloc",
    "malloc_*",
    "*.localalias"
    "free",
    "*.isra.0",
    "alloc_perturb",
    "getdelim",
    "add_alias2.part.0",
    "tsearch",
    "*_module",
    "tfind",
    "getenv",
    "str*",
    "sysconf",
    "mem*",
    "getpagesize",
    "cfree",
    "sbrk",
    "pthread_*",
    "*getenv",
    "brk",
    "*.part.0",
    "new_composite_name",
    "*textdomain",
    "*_langinfo*",
    "frame_dummy",
    "xtrace_init",
    "check_dev_tty",
    "mbs*", "hash_*", "*_variable*", "*.constprop.0", "alias_*", "var_lookup", "*_word", "*_word_*", "word_*", "*_words", "procsub_*", "notify_and_cleanup", "*getc", "fgets*"
    "execute_connection",
    "*_internal",
    "*_parser_*"
    "brace_*"
    "*printf*",
    "*command*",
    "*_frame",
    "yyparse",
    "parse_*",
    "*_stream",
    "sigemptyset*",
    "*array*",
    "*shell*",
    "itos",
    "*pipestatus*",
    "param_*",
    "*_list",
    "list_*",
    "*flush*",
    "*_builtin",
    "*_dollar_*",
    "htab_*",
    "bfd_*",
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
