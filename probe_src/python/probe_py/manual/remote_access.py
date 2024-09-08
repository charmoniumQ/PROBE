import dataclasses
import base64
from typing import Union, Any

from probe_py.manual.persistent_provenance import (
    InodeVersion,
    Inode,
    get_prov_upstream,
    Process,
    InodeMetadataVersion,
)
import struct
import xdg_base_dirs
import random
import pickle
import datetime
import json
import os
import socket
import subprocess
import pathlib
import typer
import yaml
from probe_py.manual.scp import extract_port_from_scp_command, parse_and_translate_scp_command
import typing

PROBE_HOME = xdg_base_dirs.xdg_data_home() / "PROBE"
PROCESS_ID_THAT_WROTE_INODE_VERSION = PROBE_HOME / "process_id_that_wrote_inode_version"
PROCESSES_BY_ID = PROBE_HOME / "processes_by_id"


@dataclasses.dataclass
class Host:
    network_name: str | None
    username: str | None

    def get_address(self) -> str | None:
        if self.username is None and self.network_name is None:
            return ""
        elif self.username is None:
            return self.network_name
        else:
            return f"{self.username}@{self.network_name}"


def copy(cmd: list[str]) -> None:
    # 1. get the src_inode_version and src_inode_metadata
    # 2. upload the files
    # 3. get process closure and file_writes
    # 4. get remote home for dest
    # 5. create the two directories on dest
    # 6. upload src_inode version to the destination
    # 7. upload process that wrote the file, file to dest
    #  do this for the dest
    # 8. generate random_pid to refer to the process
    # 9. create an scp process json
    # 10. added reference to scp process id to the dest inode version
    # 11. copy the scp process to the file on dest
    # Extract port from SCP command
    sources, ssh_options = parse_and_translate_scp_command(cmd)
    port = extract_port_from_scp_command(cmd)
    destination = cmd[-1]
    dest_host, dest_path = get_dest_host_and_path(destination)

    cmd.insert(0, "scp")
    upload_files(cmd)
    for source in sources:
        src, src_file_path = get_dest_host_and_path(source)
        src_inode, src_inode_metadata, process_closure, inode_version_writes = get_source_info(src, src_file_path, ssh_options)
        success = prov_upload(process_closure, inode_version_writes, dest_host, dest_path, src_file_path, ssh_options, port, src_inode, src_inode_metadata, cmd)
        if not success:
            print(f"Upload of prov info to destination {dest_host.get_address()} for f{src.get_address()}:{src_file_path}")

def prov_upload(process_closure: typing.Mapping[int, Process],
                inode_version_writes: typing.Mapping[InodeVersion, int | None], destination: Host,
                dest_path: pathlib.Path, source_file_path: pathlib.Path, ssh_options: list[str], port: int,
                src_inode_version: InodeVersion, src_inode_metadata: InodeMetadataVersion, cmd: list[str])->bool:
    try:
        remote_host = destination.network_name
        for inode_version, process_id in inode_version_writes.items():
            inode_version_path = PROCESS_ID_THAT_WROTE_INODE_VERSION / str(inode_version.str_id())
            if process_id is not None:
                # Write process_id to the file
                inode_version_path.write_text(json.dumps(process_id))
            else:
                # If process_id is None, you can write a placeholder or handle it as needed
                inode_version_path.write_text("null")

        for process_id, process in process_closure.items():
            process_path = PROCESSES_BY_ID / str(process_id)
            # Convert process object to JSON and save it back to file
            process_path.write_text(json.dumps(process, indent=4))

        dest_path = pathlib.Path(os.path.join(dest_path, os.path.basename(source_file_path)))
        if remote_host is not None:

            dest_inode_version, dest_inode_metadata = get_file_info_on_remote(destination, dest_path,
                                                                            ssh_options)
            remote_home_dest = pathlib.Path(get_remote_home(destination, ssh_options))
            create_directories_on_remote(remote_home_dest, destination, ssh_options)
            process_by_id_remote = (
                    remote_home_dest / "processes_by_id"
            )
            remote_process_id_that_wrote_inode_version = (
                    remote_home_dest
                    / "process_id_that_wrote_inode_version"
            )
            user_name_and_ip = destination.get_address()

            for inode_version, process_id in inode_version_writes.items():
                inode_version_path = PROCESS_ID_THAT_WROTE_INODE_VERSION / str(inode_version)
                scp_command = [
                    "scp",
                    "-P",
                    str(port),
                    str(inode_version_path),
                    f"{user_name_and_ip}:{remote_process_id_that_wrote_inode_version}",  # Remote file path
                ]
                upload_files(scp_command)

            for process_id, process in process_closure.items():
                process_path = PROCESSES_BY_ID / str(process_id)
                scp_command = [
                    "scp",
                    "-P",
                    str(port),
                    str(process_path),
                    f"{user_name_and_ip}:{process_by_id_remote}",
                ]
                upload_files(scp_command)
                subprocess.run(scp_command, check=True)
                create_remote_dest_inode_and_process(src_inode_version, src_inode_metadata, remote_home_dest,
                                                    dest_inode_version,
                                                    dest_inode_metadata, destination, port, cmd, ssh_options)
        else:
            dest_inode_version, dest_inode_metadata = get_file_info_on_local(dest_path)
            # process_by_id and process_id_that_wrote_inode_version are not transferred to destination as source and destination both are local
            create_local_dest_inode_and_process(src_inode_version, src_inode_metadata, dest_inode_version,
                                                dest_inode_metadata, cmd)
        return True
    except Exception:
        return False


def get_dest_host_and_path(address: str) -> tuple[Host, pathlib.Path]:
    network, user_name = None, None
    if ":" in address:
        user_name_and_network, file_path = address.split(":")
        if "@" in user_name_and_network:
            user_name, network = user_name_and_network.split("@")
    else:
        file_path = address
    host = Host(network, user_name)
    return host, pathlib.Path(file_path)

def get_source_info(source: Host, source_file_path: pathlib.Path, ssh_options: list[str]) -> tuple[
    InodeVersion, InodeMetadataVersion, typing.Mapping[int, Process], typing.Mapping[InodeVersion, int | None]]:
    username = source.username
    network_name = source.network_name
    if username is None and network_name is None:
        src_inode_version, src_inode_metadata = get_file_info_on_local(source_file_path)
        host = "local"
    else:
        src_inode_version, src_inode_metadata = get_file_info_on_remote(source, source_file_path, ssh_options)
        host = "remote"
    process_closure, inode_version_writes = get_prov_upstream(src_inode_version, host)
    return src_inode_version, src_inode_metadata, process_closure, inode_version_writes


def create_directories_on_remote(remote_home: pathlib.Path, remote: Host, ssh_options: list[str]) -> None:
    remote_directories = [
        f"{remote_home}/processes_by_id",
        f"{remote_home}/process_id_that_wrote_inode_version",  # Add more directories as needed
    ]
    remote_scp_address = remote.get_address()
    mkdir_command = [
        "ssh",
        f"{remote_scp_address}",
    ]

    for option in ssh_options:
        mkdir_command.insert(-1, option)

    for directory in remote_directories:
        mkdir_command.append(f"mkdir -p {directory}", )
        subprocess.run(mkdir_command, check=True)
        mkdir_command.pop()


def create_local_dest_inode_and_process(src_inode_version: InodeVersion, src_inode_metadata: InodeMetadataVersion,
                                        dest_inode_version: InodeVersion, dest_inode_metadata: InodeMetadataVersion,
                                        cmd: list[str]) -> None:

    PROBE_HOME = xdg_base_dirs.xdg_data_home() / "PROBE"
    PROCESS_ID_THAT_WROTE_INODE_VERSION = PROBE_HOME / "process_id_that_wrote_inode_version"
    PROCESSES_BY_ID = PROBE_HOME / "processes_by_id"

    random_pid = generate_random_pid()
    process_id_localinode_path_local = PROCESS_ID_THAT_WROTE_INODE_VERSION / dest_inode_version.str_id()
    os.makedirs(os.path.dirname(process_id_localinode_path_local), exist_ok=True)

    # Write the random_pid to the file
    with open(process_id_localinode_path_local, 'w') as file:
        file.write(str(random_pid))

    scp_process_json = get_process(src_inode_version, src_inode_metadata, dest_inode_version, dest_inode_metadata,
                                       random_pid, cmd)

    scp_process_path = PROCESSES_BY_ID / str(random_pid)
    with open(scp_process_path, "w") as file:
        file.write(scp_process_json)


def create_remote_dest_inode_and_process(src_inode_version: InodeVersion, src_inode_metadata: InodeMetadataVersion,
                                         remote_home: pathlib.Path, dest_inode_version: InodeVersion,
                                         dest_inode_metadata: InodeMetadataVersion, remote: Host,
                                         port: int, cmd: list[str], ssh_options: list[str]) -> None:
    random_pid = generate_random_pid()
    process_id_remoteinode_path_remote = (
            remote_home
            / "process_id_that_wrote_inode_version" / dest_inode_version.str_id()
    )

    remote_scp_address = remote.get_address()
    check_and_create_remote_file(remote, port, process_id_remoteinode_path_remote)
    create_file_command = [
        "ssh",
        f"{remote_scp_address}",
    ]
    for option in ssh_options:
        create_file_command.insert(-1, option)
    create_file_command.append(f"printf {random_pid} > {process_id_remoteinode_path_remote}")
    subprocess.run(create_file_command, check=True)
    # create Process object for scp
    scp_process_json = get_process(src_inode_version, src_inode_metadata, dest_inode_version, dest_inode_metadata,
                                       random_pid, cmd)
    scp_process_path = remote_home / "processes_by_id"
    local_path = f"/tmp/{random_pid}.json"
    with open(local_path, "w") as file:
        file.write(scp_process_json)
    scp_command = [
        "scp",
        f"-P {port}",
        local_path,
        f"{remote_scp_address}:{scp_process_path}",
    ]
    upload_files(scp_command)


def get_process(src_inode_version: InodeVersion, src_inode_metadata: InodeMetadataVersion,
                    dest_inode_version: InodeVersion, dest_inode_metadata: InodeMetadataVersion, random_pid: int,
                    cmd: list[str]) -> str:
    # create Process object for scp
    input_nodes = frozenset([src_inode_version])
    input_inode_metadata = frozenset([src_inode_metadata])
    output_inodes = frozenset([dest_inode_version])
    output_inode_metadata = frozenset([dest_inode_metadata])
    time = datetime.datetime.today()
    env: tuple[tuple[str, str], ...] = ()
    scp_process = Process(
        input_nodes,
        input_inode_metadata,
        output_inodes,
        output_inode_metadata,
        time,
        tuple(cmd),
        random_pid,
        env,
        pathlib.Path(),
    )

    scp_process_json = process_to_json(scp_process)
    return scp_process_json


def get_stat_results_remote(remote: Host, file_path: pathlib.Path, ssh_options: list[str]) -> bytes:
    remote_scp_address = remote.get_address()
    ssh_command = [
        "ssh",
        f"{remote_scp_address}",
    ]
    for option in ssh_options:
        ssh_command.insert(-1, option)

    ssh_command.append(f'stat -c "size: %s\nmode: 0x%f\n" {file_path}')
    try:
        result = subprocess.run(ssh_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout
        stats = yaml.safe_load(output)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Error retrieving stat for {file_path}: {e.stderr.decode()}")

    file_size = stats["size"]
    return bytes(file_size)


def process_to_json(process: Process) -> str:
    process_dict = dataclasses.asdict(process)

    def custom_serializer(obj: object) -> Union[list[str], str, dict[str, Any]]:
        if isinstance(obj, frozenset):
            return list(obj)  # Convert frozenset to list
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()  # Convert datetime to ISO format string
        elif isinstance(obj, pathlib.Path):
            return str(obj)  # Convert Path to string
        elif isinstance(obj, tuple):
            return list(obj)  # Convert tuple to list
        elif isinstance(obj, InodeVersion) or isinstance(obj, Inode) or isinstance(obj, InodeMetadataVersion):
            return obj.__dict__
        elif isinstance(obj, bytes):
            return base64.b64encode(obj).decode('ascii')
        raise TypeError(f"Type {type(obj)} not serializable")

    # Convert the dictionary to JSON
    return json.dumps(process_dict, default=custom_serializer, indent=4)


def generate_random_pid() -> int:
    min_pid = 1
    max_pid = 32767
    random_pid = random.randint(min_pid, max_pid)
    return random_pid


def upload_files(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        typer.echo("File transfer successful.")
    except subprocess.CalledProcessError as e:
        # Capture and print the error message
        typer.echo(f"Error occurred during file transfer: {e}")
        typer.echo(f"Exit code: {e.returncode}")
        typer.echo(f"Error output: {e.stderr}")


def check_and_create_remote_file(remote: Host, port: int, remote_file_path: pathlib.Path) -> None:
    try:
        remote_address = remote.get_address()
        # Check if the file exists on the remote server
        check_command = f"ssh -p {port} {remote_address} 'test -f {remote_file_path} && echo \"File exists\" || echo \"File does not exist\"'"
        result = subprocess.run(check_command, shell=True, check=True, capture_output=True, text=True)
        output = result.stdout.strip()
        if output == "File does not exist":
            # Create the file if it does not exist
            create_command = f"ssh -p {port} {remote_address} 'touch {remote_file_path}'"
            subprocess.run(create_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print(f"Error output: {e.stderr}")
    except Exception as e:
        print(f"An error occurred: {e}")


def get_remote_home(remote: Host, ssh_options: list[str]) -> pathlib.Path:
    remote_xdg = get_remote_xdg_data_home(remote, ssh_options)
    if remote_xdg != "":
        remote_home = pathlib.Path(f"home/{remote_xdg}/.local/share") / "PROBE"
    else:
        home = get_remote_home_env(remote, ssh_options)
        remote_home = pathlib.Path(f"{home}/.local/share") / "PROBE"
    return remote_home


def get_remote_xdg_data_home(remote: Host, ssh_options: list[str]) -> str | None:
    try:
        remote_scp_address = remote.get_address()
        ssh_command = [
            "ssh",
            f"{remote_scp_address}",
        ]
        for option in ssh_options:
            ssh_command.insert(-1, option)
        ssh_command.append("echo $XDG_DATA_HOME", )
        result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)
        xdg_data_home = result.stdout.strip()
        return xdg_data_home
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving XDG_DATA_HOME: {e}")
        # customary case when $HOME is None
        return "/homeless-shelter"


# @functools.lru_cache(maxsize=128)
def get_remote_home_env(remote: Host, ssh_options: list[str]) -> str | None:
    remote_scp_address = remote.get_address()
    try:
        ssh_command = [
            "ssh",
            f"{remote_scp_address}",
        ]
        for option in ssh_options:
            ssh_command.insert(-1, option)
        ssh_command.append("echo $HOME")
        result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)
        home = result.stdout.strip()
        return home
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving XDG_DATA_HOME: {e}")
        return "/homeless-shelter"


def get_file_info_on_local(file_path: pathlib.Path) -> tuple[InodeVersion, InodeMetadataVersion]:
    stat_info = os.stat(file_path)
    device_major = os.major(stat_info.st_dev)
    device_minor = os.minor(stat_info.st_dev)
    inode_val = stat_info.st_ino
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    packed_ip = socket.inet_aton(ip_address)
    host = struct.unpack("!I", packed_ip)[0]

    # c uses mtime in nanoseconds
    mtime_micro_seconds = stat_info.st_mtime
    mtime = int(mtime_micro_seconds * 1_000_000_000)

    size = stat_info.st_size
    inode = Inode(host, device_major, device_minor, inode_val)
    inode_version = InodeVersion(inode, mtime, size)
    stat_results = os.stat(file_path)
    serialized_stat_results = pickle.dumps(stat_results)
    inode_metadata = InodeMetadataVersion(
        inode_version, serialized_stat_results
    )
    return inode_version, inode_metadata


def get_file_info_on_remote(remote: Host, file_path: pathlib.Path, ssh_options: list[str]) -> tuple[
    InodeVersion, InodeMetadataVersion]:
    remote_address = remote.get_address()
    command = [
        "ssh",
        f"{remote_address}",
    ]
    for option in ssh_options:
        command.insert(-1, option)
    command.append(f'stat -c "%D %i %s %Y" {file_path}', )
    process = subprocess.run(command, check=True, capture_output=True, text=True)

    output = process.stdout.strip()
    device_hex, str_inode, str_size, str_mtime = output.split()

    inode_val = int(str_inode)
    size = int(str_size)
    mtime = int(str_mtime) * 1_000_000_000

    # Get host information
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    packed_ip = socket.inet_aton(ip_address)
    host = struct.unpack("!I", packed_ip)[0]

    command.pop()
    command.append(
        f'python3 -c \'import os, json; stat_info = os.stat("{file_path}"); device_id = stat_info.st_dev; result = {{"device_major": os.major(device_id), "device_minor": os.minor(device_id)}}; print(json.dumps(result))\'')

    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stdout.strip()
    data = json.loads(output)
    device_major = data["device_major"]
    device_minor = data["device_minor"]
    inode = Inode(host, device_major, device_minor, inode_val)
    inode_version = InodeVersion(inode, mtime, size)
    stat_results = get_stat_results_remote(remote, file_path, ssh_options)
    inode_metadata = InodeMetadataVersion(inode_version, stat_results)
    return inode_version, inode_metadata
