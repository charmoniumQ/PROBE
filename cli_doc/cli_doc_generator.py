import subprocess
import re
from itertools import chain

# collecting commands within the "Commands" heading
def extract_commands(lns):
    cmd_arr = []
    collecting = False
    for line in lns:
        line = line.strip()
        if not line:
            continue

        if line.startswith("Commands:"):
            collecting = True
            continue

        if collecting and line.endswith(":"):
            break

        if collecting:
            cmd_arr.append(line.split()[0])

    if "help" in cmd_arr:
        cmd_arr.remove("help")

    return cmd_arr

def extract_options(lns):
    opts_arr = []
    collecting = False
    for line in lns:
        line = line.strip()
        if not line:
            continue

        if line.startswith("Options:"):
            collecting = True
            continue

        if collecting and line.endswith(":"):
            break

        if collecting:
            opts_arr.append([line])

    return opts_arr

def parse_options(opts):
    parsed_lines = []
    for line in opts:
        match = re.match(r"(\S+),? ?(\S+)?\s+(.*)", line)
        if match:
            short_option = match.group(1).strip() if match.group(1) else ""
            long_option = match.group(2).strip() if match.group(2) else ""
            description = match.group(3).strip()
            parsed_lines.append([short_option, long_option, description])
    return parsed_lines

def parse_options_for_exportcmd(option):
    if len(option) > 2:
        yield option[0], option[1], " ".join(option[2])
    elif len(option) > 1:
        yield option[0], option[1], ""
    else:
        yield option[0], "", ""

def extract_arguments(arg_lines):
    arg_mode = False
    arr = []
    for each_line in arg_lines:
        if arg_mode and not each_line.startswith("╰─"):
            arr.append(each_line)
        if each_line.startswith("╭─ Arguments"):
            arg_mode = True
            pass
        elif each_line.startswith("╰─"):
            break
    return arr


def process_lines(lines):
    split_lines = []
    processed_lines = []
    for line in lines:
        remove_sp_char = line.replace('│', '').replace('*', '').strip()
        cleaned_lines = [i for i in remove_sp_char.split(" ") if i != '']
        split_lines.append(cleaned_lines)

    for i in split_lines:
        processed_lines.append([i[0],i[1],i[2:]])

    return processed_lines


def write_to_readme(cmd, options):
    with open("README.md", "a") as readme_md:
        readme_md.write(f"### probe {cmd}\n\n")
        readme_md.write("| Option | Alternative | Description |\n")
        readme_md.write("|--------|-------------|-------------|\n")
        for op in options:
            flat_option = list(chain(*parse_options(op)))
            short = flat_option[0] if len(flat_option) > 0 else ""
            long = flat_option[1] if len(flat_option) > 1 else ""
            description = flat_option[2] if len(flat_option) > 2 else ""
            readme_md.write(f"| {short} | {long} | {description} |\n")
        readme_md.write("\n")

def write_to_readme_exported(cmd, options):
    with open("README.md", "a") as readme_md:
        readme_md.write(f"### probe {cmd}\n\n")
        readme_md.write("| Option | Parameter | Description |\n")
        readme_md.write("|--------|-------------|-------------|\n")
        for op in options:
            flat_option = list(chain(*parse_options_for_exportcmd(op)))
            short = flat_option[0] if len(flat_option) > 0 else ""
            long = flat_option[1] if len(flat_option) > 1 else ""
            description = flat_option[2] if len(flat_option) > 2 else ""
            readme_md.write(f"| {short} | {long} | {description} |\n")
        readme_md.write("\n")

if __name__ == '__main__':
    result = subprocess.run("probe help",
                            shell=True,
                            check=False,
                            capture_output=True,
                            text=True)

    output = result.stdout
    lines = output.split("\n")

    commands_array = extract_commands(lines)

    cmds = ["validate","ssh"]
    export_cmd = ["ops-graph","dataflow-graph","debug-text","docker-image","oci-image","makefile"]

    # Clear previous content in README.md
    with open("README.md", "w") as readme:
        readme.write("# Commands and Options\n\n")

    for command in commands_array:
        cmd_doc = subprocess.run(f"probe help {command}",
                                 shell=True,
                                 check=False,
                                 capture_output=True,
                                 text=True)

        each_output = cmd_doc.stdout
        opt_lines = each_output.split("\n")
        opt_arr = extract_options(opt_lines)
        write_to_readme(command, opt_arr)

    for command in cmds:
        cmd_doc = subprocess.run(f"probe {command} --help",
                                 shell=True,
                                 check=False,
                                 capture_output=True,
                                 text=True)
        opt_lines = [i.strip() for i in cmd_doc.stdout.split("\n") if i.strip()]
        write_to_readme_exported(command,process_lines(extract_arguments(opt_lines)))


    for command in export_cmd:
        cmd_doc = subprocess.run(f"probe export {command} --help",
                                 shell=True,
                                 check=False,
                                 capture_output=True,
                                 text=True)
        opt_lines = [i.strip() for i in cmd_doc.stdout.split("\n") if i.strip()]
        write_to_readme_exported(f"export {command}",process_lines(extract_arguments(opt_lines)))
