def parse_ssh_args(ssh_args: list[str]) -> tuple[list[str], str, list[str]]:

    one_arg_options = set("BbcDEeFIiJLlmOoPpRSWw")
    no_arg_options = set("46AaCfGgKkMNnqsTtVvXxYy")

    state = 'start'
    i = 0
    flags = []
    destination = None
    remote_host = []

    while i < len(ssh_args):
        curr_arg = ssh_args[i]

        if state == 'start':
            if curr_arg.startswith("-"):
                state = 'flag'
            elif destination is not None:
                state = 'cmd'
            else:
                state = 'destination'

        elif state == 'flag':
            opt = curr_arg[-1]
            if opt in one_arg_options:
                state = 'one_arg'
            elif opt in no_arg_options:
                flags.append(curr_arg)
                state = 'start'
            i += 1

        elif state == 'one_arg':
            flags.extend([ssh_args[i - 1], curr_arg])
            state = 'start'
            i += 1

        elif state == 'destination':
            if destination is None:
                destination = curr_arg
                state = 'start'
            else:
                state = 'cmd'
                continue
            i += 1

        elif state == 'cmd':
            remote_host.extend(ssh_args[i:])
            break

    assert destination is not None
    return flags, destination, remote_host

