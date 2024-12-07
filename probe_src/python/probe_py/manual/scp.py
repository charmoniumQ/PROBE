from pathlib import Path
import re
import itertools
import subprocess
from probe_py.manual.remote_access import Host, HostPath, copy_provenance


def scp_with_provenance(scp_args: list[str]) -> int:
    """
    1. get the src_inode_version and src_inode_metadata
    2. upload the files
    3. get process closure and file_writes
    4. get remote home for dest
    5. create the two directories on dest
    6. upload src_inode version to the destination
    7. upload process that wrote the file, file to dest
     do this for then dest
    8. generate random_pid to refer to the process
    9. create an scp process json
    10. added reference to scp process id to the dest inode version
    11. copy the scp process to the file on dest
    """
    proc = subprocess.run(["scp", *scp_args], capture_output=False, check=False)
    if proc.returncode == 0:
        sources, destination = parse_scp_args(scp_args)
        for source in sources:
            copy_provenance(source, destination, ["scp", *scp_args])
        return 0
    else:
        return proc.returncode


def parse_scp_args(scp_args: list[str]) -> tuple[list[HostPath], HostPath]:
    """Converts arguments to scp to a list of sources and a destination

    Note that the Host type contains the instructions/options needed to connect to it.
    """
    scp_no_arg_options = {'-3', '-B', '-O', '-p', '-q', '-R', '-r', '-T'}
    scp_one_arg_options = {'-3', '-B', '-D', '-l', '-S', '-X'}
    common_no_arg_options = {'-4', '-6', '-A', '-C', '-v', '-q', '-v'}
    common_one_arg_options = {'-c', '-F', '-i', '-J', '-o', '-v', '-q'}
    mapped_one_arg_options = {
        '-P': '-p',
    }

    scp_options = []
    ssh_options = []
    sources = []

    # Replace ["-abc"] with ["-a", "-b", "-c"]
    # to make parsing easier

    # TODO: This is not strictly accurate.
    # I would need to read SCP's source code or play around with it a bit to know for sure.
    # I believe "scp -oProxyCommand=foobar source dest" is valid
    scp_args = list(itertools.chain.from_iterable([
        [f"-{option}" for option in arg[1:]] if arg.startswith("-") else [arg]
        for arg in scp_args
    ]))

    i = 0
    while i < len(scp_args):
        arg = scp_args[i]
        if arg.startswith("-"):
            assert len(arg) == 2, f"We should have already replaced -abc with -a -b -c, yet we have {arg}"
            if arg[1:] in scp_no_arg_options:
                scp_options.append(arg)
            elif arg[1:] in scp_one_arg_options:
                scp_options.append(arg)
                i += 1
                arg = scp_args[i]
                scp_options.append(arg)
            elif arg[1:] in common_no_arg_options:
                scp_options.append(arg)
                ssh_options.append(arg)
            elif arg[1:] in common_one_arg_options:
                scp_options.append(arg)
                ssh_options.append(arg)
                i += 1
                arg = scp_args[i]
                scp_options.append(arg)
                ssh_options.append(arg)
            elif arg[1:] in mapped_one_arg_options:
                scp_options.append(arg)
                ssh_options.append(mapped_one_arg_options[arg])
                i += 1
                arg = scp_args[i]
                scp_options.append(arg)
                ssh_options.append(arg)
            else:
                raise NotImplementedError(f"Unrecognized option {arg}")
        else:
            if match := re.match(scp_url_regex, arg):
                this_scp_options = scp_options[:]
                this_ssh_options = ssh_options[:]
                if match.group("port"):
                    this_scp_options.append("-P")
                    this_scp_options.append(match.group("port"))
                    this_ssh_options.append("-P")
                    this_ssh_options.append(match.group("port"))
                sources.append(HostPath(
                    Host(match.group("host"), match.group("user"), None, this_ssh_options, this_scp_options),
                    Path(match.group("path") if match.group("path") else "")
                ))
            elif match := re.match(scp_path_regex, arg):
                sources.append(HostPath(
                    Host(None, None, [], []),
                    Path(arg)
                ))
            elif match := re.match(scp_address_regex, arg):
                sources.append(HostPath(
                    Host(match.group("host"), match.group("user"), ssh_options, scp_options),
                    Path(match.group("path") if match.group("path") else "")
                ))
            else:
                print(scp_url_regex)
                print(scp_address_regex)
                raise RuntimeError(f"Invalid scp argument {arg}")
        i += 1
    return sources[:-1], sources[-1]



# Define some regexp helpers.
# In my opinion, "spelling" the regexp this way makes it much more readable.
def concat(*args: str) -> str:
    return "".join(args)
def optional(arg: str) -> str:
    return f"(?:{arg})?"
def named_group(name: str, arg: str) -> str:
    return f"(?P<{name}>{arg})?"
def whole_string(arg: str) -> str:
    return re.compile("^" + arg + "$")

# TODO: do options only apply to the host following it?
# E.g., does scp -J host-A host-B host-C only apply a jump-host to the host-B?

# https://superuser.com/questions/1516008/what-does-please-enter-a-username-matching-the-regular-expression-configured-vi
unix_username_regex = "[a-z][-a-z0-9_]*"
host_regex = r"[a-zA-Z0-9\.-]{1,63}"
# scp://[user@]host[:port][/path]
scp_url_regex = whole_string(concat(
    "scp://",
    optional(concat(named_group("user", unix_username_regex), "@")),
    named_group("host", host_regex),
    optional(concat(":", named_group("port", r"\d+"))),
    optional(concat("/", named_group("path", ".*"))),
))
path_regex = "[^:@]*"
scp_path_regex = whole_string(path_regex)
# [user@]host[:path]
scp_address_regex = whole_string(concat(
    optional(concat(named_group("user", unix_username_regex), "@")),
    named_group("host", host_regex),
    optional(concat(":", named_group("path", path_regex))),
))
