import re

def extract_port_from_scp_command(args: list[str]) -> int:
    port = None
    for i in range(len(args)):
        if args[i] == '-P' and i + 1 < len(args):
            port = args[i + 1]
            break
        elif re.match(r'^-P\d+$', args[i]):
            port = args[i][2:]
            break
    if port is None:
        return 22
    return int(port)

def parse_and_translate_scp_command(cmd: list[str]) -> tuple[list[str], list[str]]:
    ssh_options = []
    sources = []
    common_options = {'-4', '-6', '-A', '-C', '-o', '-i', '-v', '-q'}
    option_mapping = {
        '-P': '-p',
    }
    one_arg_options = {"-o", "-i", "-P"}

    i = 0
    while i < len(cmd):
        arg = cmd[i]
        unknown_option = True
        if arg in option_mapping:
            ssh_options.append(option_mapping[arg])
            unknown_option = False
        elif arg in common_options:
            unknown_option = False
            ssh_options.append(arg)

        if unknown_option:
            if arg.startswith('-'):
                # Handle unknown or unmapped scp options (assumed to be scp-only)
                pass  # Add any specific handling for unrecognized options if needed
            else:
                # Consider the argument as a source or destination if it's not an option
                sources.append(arg)
        else:
            if arg in one_arg_options and i+1 < len(cmd):
                ssh_options.append(cmd[i + 1])
                i += 1
        i += 1
    sources.pop()
    return sources, ssh_options