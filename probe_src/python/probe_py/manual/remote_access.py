import dataclasses
import base64
from typing import Union, Any

from probe_py.manual.persistent_provenance import (
    Inode,
    InodeVersion,
    InodeMetadata,
    get_prov_upstream,
    Process,
)
import itertools
import xdg_base_dirs
import random
import datetime
import json
import os
import shlex
import random
import subprocess
import pathlib
import yaml
import typing


@dataclasses.dataclass(frozen=True)
class Host:
    network_name: str | None

    # Later on, these fields may be properties that get computed based on other fields.
    username: str
    ssh_options: list[str]
    scp_options: list[str]

    def get_address(self) -> str | None:
        if self.username is None and self.network_name is None:
            return ""
        elif self.username is None:
            return self.network_name
        else:
            return f"{self.username}@{self.network_name}"

    @property
    def local(self) -> bool:
        return self.username is None and self.network_name is None


@dataclasses.dataclass(frozen=True)
class HostPath:
    host: Host
    path: pathlib.Path


def copy_provenance(source: HostPath, destination: HostPath, cmd: tuple[str, ...]) -> None:
    provenance_info_source = lookup_provenance_source(source)
    provenance_info_destination = lookup_provenance_destination(source, destination)
    provenance_info = augment_provenance(provenance_info_source, provenance_info_destination, cmd)
    # TODO: Support uploading all the provenance_info from mulitple sources at once
    # Either copy_provenance should take multiple sources
    # Or it should return the provenance rather than uploading it
    # so the caller can upload them all together
    upload_provenance(destination.host, provenance_info)


ProvenanceInfo: typing.TypeAlias = tuple[
    list[InodeVersion],
    list[InodeMetadata],
    typing.Dict[int, Process],
    typing.Dict[InodeVersion, int | None],
]


def lookup_provenance_source(source: HostPath) -> ProvenanceInfo:
    """Returns the provenance info associated with source

    If source is a directory, returns the provenance info for each file contained in the directory recursively.
    """
    if source.host.local:
        return lookup_provenance_local(source.path, True)
    else:
        return lookup_provenance_remote(source.host, source.path, True)

def lookup_provenance_destination(source: HostPath, destination: HostPath) -> ProvenanceInfo:
    source_path = source.path
    if source_path.is_dir():
        source_files = get_descendants(source_path, False)
    else:
        source_files = [source_path]

    inode_versions = []
    inode_metadatas = []
    for path in source_files:
        destination_path = destination.path / path.name
        if destination.host.local:
            inode_version, inode_metadata, _process_map, _inode_map = lookup_provenance_local(destination_path, False)
        else:
            inode_version, inode_metadata, _process_map, _inode_map = lookup_provenance_remote(destination.host, destination_path, False)
        inode_versions.extend(inode_version)
        inode_metadatas.extend(inode_metadata)

    return inode_versions, inode_metadatas, {}, {}

def augment_provenance(
        source_provenance_info: ProvenanceInfo,
        destination_provenance_info: ProvenanceInfo,
        cmd: tuple[str, ...],
) -> ProvenanceInfo:
    """Given provenance_info of files on a previous host, insert nodes to represent a remote transfer to destination."""
    source_inode_versions, source_inode_metadatas, process_closure, inode_writes = source_provenance_info
    destination_inode_versions, destination_inode_metadatas, _process_closure, _inode_writes = destination_provenance_info
    scp_process_id = generate_random_pid()
    time = datetime.datetime.today()
    env: tuple[tuple[str, str], ...] = ()
    while scp_process_id in process_closure:
        scp_process_id = generate_random_pid()
    scp_process = Process(
        source_inode_versions,
        source_inode_metadatas,
        destination_inode_versions,
        destination_inode_metadatas,
        time,
        tuple(cmd),
        scp_process_id,
        env,
        pathlib.Path(),
    )
    process_closure[scp_process_id] = scp_process
    for destination_inode_version in destination_inode_versions:
        inode_writes[destination_inode_version] = scp_process_id

    return destination_inode_versions, destination_inode_metadatas , process_closure, inode_writes

def upload_provenance(dest: Host, provenance_info: ProvenanceInfo) -> None:
    if dest.local:
        upload_provenance_local(provenance_info)
    else:
        upload_provenance_remote(dest, provenance_info)


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


def get_descendants(root: pathlib.Path, include_directories: bool) -> list[pathlib.Path]:
    queue = [root]
    ret = []
    while queue:
        path = queue.pop()
        if path.is_dir():
            queue.extend(path.iterdir())
            if include_directories:
                ret.append(path)
        else:
            ret.append(path)
    return ret


def lookup_provenance_local(path: pathlib.Path, get_persistent_provenance: bool) -> ProvenanceInfo:
    if path.is_dir():
        inode_versions = [
            InodeVersion.from_local_path(descendant)
            for descendant in get_descendants(path, False)
        ]
        inode_metadatas = [
            InodeMetadata.from_local_path(descendant)
            for descendant in get_descendants(path, True)
        ]
    else:
        inode_versions = [InodeVersion.from_local_path(path)]
        inode_metadatas = [InodeMetadata.from_local_path(path)]
    if get_persistent_provenance:
        process_map, inode_map = get_prov_upstream(inode_versions, "local")
        return inode_versions, inode_metadatas, process_map, inode_map
    return inode_versions, inode_metadatas, {}, {}



def lookup_provenance_remote(host: Host, path: pathlib.Path, get_persistent_provenance: bool) -> ProvenanceInfo:
    address = host.get_address()
    assert address is not None
    proc = subprocess.run(
        [
            "ssh",
            *host.ssh_options,
            address,
            "sh", "-c", ";".join([
                "node_name_file=${XDG_CACHE_HOME:-$HOME/.cache}/PROBE/node_name",
                "[ ! -f $node_name_file ] && echo -n $(tr -dc 'A-F0-9' < /dev/urandom | head -c8).$(hostname) > $node_name_file",
                # First field is node_name
                "cat $node_name_file",

                # I will use null-bytes as separators, because spaces (and even newlines) can occur in the filenames
                # Second field will be PWD
                'echo -e "\0$PWD\0"',

                # The rest of the fields will be each of 9 entries in the following printf
                f"find -printf '%p\0%D\0%i\0%T@\0%s\0%m\0%n\0%U\0%G\0' {shlex.quote(str(path))}"
            ]),
        ],
        capture_output=True,
        check=True,
        text=False,
    )

    fields = proc.stdout.split(b"\0")
    node_name = fields[0]
    #cwd = pathlib.Path(fields[1])
    inode_metadatas = []
    inode_versions = []
    for _child_path, device, inode, mtime, size, mode, nlink, uid, gid in itertools.batched(fields[2:], 9):
        inode = Inode(node_name, os.major(int(device)), os.minor(int(device)), int(inode))
        inode_versions.append(InodeVersion(inode, int(mtime), int(size)))
        inode_metadatas.append(InodeMetadata(inode, int(mode), int(nlink), int(uid), int(gid)))

    if not get_persistent_provenance:
        return inode_versions, inode_metadatas, {}, {}

    # TODO: Implement this
    proc = subprocess.run(
        [
            "ssh",
            *host.ssh_options,
            address,
            "sh", "-c", ";".join([
                "probe_data=${XDG_DATA_HOME:-$HOME/.local/share}/PROBE",
                "process_by_id=${probe_data}/process_id_that_wrote_inode_version",
                "process_that_wrote=${probe_data}/processes_by_id",

                # cat the relevant stuff
                *[
                    f"cat $process_by_id/{inode}.json && echo '\0'",
                    for inode in []
                ],
            ]),
        ],
        capture_output=True,
        check=True,
        text=False,
    )
    raise NotImplementedError()

    return inode_versions, inode_metadatas, {}, {}


def upload_provenance_local(provenance_info: ProvenanceInfo) -> None:
    raise NotImplementedError()


def upload_provenance_remote(dest: Host, provenance_info: ProvenanceInfo) -> None:
    raise NotImplementedError()


# Notes:
# - scp.py is the driver and remote_access.py is the library. This way, remote_access.py can be re-imported into ssh. It makes more sense to me.
# - Parse options completely in 1 function. Rather than have parsing scattered in different functions.
# - Parse options differently. I realized that options can be combined "scp -4iv".
# - Introduce HostPath.
# - Host should have instructions for connecting to it.
# - In some cases, the source can be a whole directory, so the provenance needs to include every descendant of that directory "**".
# - Use `find` to get inodes of remote rather than `stat`, since `find` explores directory recursively. It has a similar interface, like "%D %s %m...". I use null-bytes as separators rather than space and newline, in case the filename has space (or even new line) in it.
# - I tried to combine as many of the SSH commands into one big SSH command. E.g., always use ${XDG_CACHE_HOME:-$HOME/.cache}
# - Defined a type alias for provenance info: tuple[list[InodeVersion], list[InodeMetadata], ...]
# - I changed how InodeMetadata works: no state_result (bytes); instead individual fields of the stat results. However, not all fields are exposed with find, which limits us on what we can write right now.
# - I used (rand number, hostname) as the nodename. Hostname is human-readable; random number differentiates if the hostnames are not unique. Random number is stored in ~/.cache/PROBE/node_name, so it will be persistent.
