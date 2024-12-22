import dataclasses

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
import subprocess
import pathlib
import yaml
import typing

PROBE_HOME = xdg_base_dirs.xdg_data_home() / "PROBE"
PROCESS_ID_THAT_WROTE_INODE_VERSION = PROBE_HOME / "process_id_that_wrote_inode_version"
PROCESSES_BY_ID = PROBE_HOME / "processes_by_id"

@dataclasses.dataclass(frozen=True)
class Host:
    network_name: str | None

    # Later on, these fields may be properties that get computed based on other fields.
    username: str | None
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
    dict[int, Process],
    dict[InodeVersion, int | None],
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
        frozenset(source_inode_versions),
        frozenset(source_inode_metadatas),
        frozenset(destination_inode_versions),
        frozenset(destination_inode_metadatas),
        time,
        tuple(cmd),
        scp_process_id,
        env,
        pathlib.Path(),
    )
    process_closure[scp_process_id] = scp_process
    process_path = PROCESSES_BY_ID / f"{str(scp_process_id)}.json"
    os.makedirs(process_path.parent, exist_ok=True)
    with process_path.open("w") as f:
        json.dump(scp_process.to_dict(), f)
    for destination_inode_version in destination_inode_versions:
        inode_writes[destination_inode_version] = scp_process_id

    return destination_inode_versions, destination_inode_metadatas , process_closure, inode_writes

def upload_provenance(dest: Host, provenance_info: ProvenanceInfo) -> None:
    if dest.local:
        upload_provenance_local(provenance_info)
    else:
        upload_provenance_remote(dest, provenance_info)

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
            InodeVersion.from_local_path(descendant, None)
            for descendant in get_descendants(path, False)
        ]
        inode_metadatas = [
            InodeMetadata.from_local_path(descendant, None)
            for descendant in get_descendants(path, True)
        ]
    else:
        inode_versions = [InodeVersion.from_local_path(path, None)]
        inode_metadatas = [InodeMetadata.from_local_path(path, None)]
    if get_persistent_provenance:
        process_map, inode_map = get_prov_upstream(inode_versions, "local")
        return inode_versions, inode_metadatas, process_map, inode_map
    return inode_versions, inode_metadatas, {}, {}



def lookup_provenance_remote(host: Host, path: pathlib.Path, get_persistent_provenance: bool) -> ProvenanceInfo:
    address = host.get_address()
    assert address is not None
    commands = [
        'node_name_file="${XDG_CACHE_HOME:-$HOME/.cache}/PROBE/node_name"',
        'mkdir -p "$(dirname "$node_name_file")"',  # Ensure directory exists
        (
            '[ ! -f "$node_name_file" ] && '
            'echo -n "$(tr -dc \'A-F0-9\' < /dev/urandom | head -c8).$(hostname)" > "$node_name_file"'
        ),
        # First field is node_name
        'cat "$node_name_file"',
        # Used | as the separator
        # Second field is PWD
        'echo -e "|$PWD|"',
        # Find command to print file details
        f'find {shlex.quote(str(path))} -exec stat -c "%n|%d|%i|%Y|%s|%a|%h|%u|%g|" {{}} \\;',
    ]

    full_command = "sh -c '" + "; ".join(commands) + "'"
    proc = subprocess.run(
        [
            "ssh",
            *host.ssh_options,
            address,
            full_command,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
    )

    fields = proc.stdout.split("|")
    node_name = fields[0]
    #cwd = pathlib.Path(fields[1])
    inode_metadatas = []
    inode_versions = []
    for _child_path, device, inode, mtime, size, mode, nlink, uid, gid in itertools.batched(fields[2:11], 10):
        inode_object = Inode(node_name, os.major(int(device)), os.minor(int(device)), int(inode))
        inode_versions.append(InodeVersion(inode_object, int(float(mtime)), int(size)))
        inode_metadatas.append(InodeMetadata(inode_object, int(mode), int(nlink), int(uid), int(gid)))

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
                "processes_by_id=${probe_data}/process_id_that_wrote_inode_version",
                "process_that_wrote=${probe_data}/processes_by_id",

                # cat the relevant stuff
                *[
                    f"cat $processes_by_id/{inode}.json && echo '\0'"
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
    destination_inode_versions, destination_inode_metadatas, augmented_process_closure, augmented_inode_writes = provenance_info

    for inode_version, process_id in augmented_inode_writes.items():
        inode_version_path = PROCESS_ID_THAT_WROTE_INODE_VERSION / f"{inode_version.str_id()}.json"
        with inode_version_path.open("w") as f:
            json.dump(process_id if process_id is not None else None, f)

    for process_id, process in augmented_process_closure.items():
        process_path = PROCESSES_BY_ID / f"{process_id}.json"
        with process_path.open("w") as f:
            json.dump(process.to_dict(), f)


def upload_provenance_remote(dest: Host, provenance_info: ProvenanceInfo) -> None:
    destination_inode_versions, destination_inode_metadatas, augmented_process_closure, augmented_inode_writes = provenance_info

    for inode_version, process_id in augmented_inode_writes.items():
        if inode_version not in destination_inode_versions:
            continue
        inode_version_path = PROCESS_ID_THAT_WROTE_INODE_VERSION / f"{inode_version.str_id()}.json"
        os.makedirs(inode_version_path.parent, exist_ok=True)
        with inode_version_path.open("w") as f:
            json.dump(process_id if process_id is not None else None, f)
    address = dest.get_address()
    assert address is not None
    echo_commands = []
    for inode_version, process_id in augmented_inode_writes.items():
        inode_version_str_id = inode_version.str_id()
        echo_commands.append(
            f"echo {shlex.quote(json.dumps(process_id))} > \"${{process_that_wrote}}/{inode_version_str_id}.json\""
        )

    for process_id, process in augmented_process_closure.items():
        echo_commands.append(
            f"echo {(json.dumps(process.to_dict()))} > \"${{processes_by_id}}/{str(process_id)}.json\""
        )

    commands = [
        'probe_data="$HOME/.local/share/PROBE"',
        'mkdir -p "$(dirname "$probe_data")"',
        'process_that_wrote="$probe_data/process_id_that_wrote_inode_version"',
        'processes_by_id="$probe_data/processes_by_id"',
        'mkdir -p "$process_that_wrote"',
        'mkdir -p "$processes_by_id"',
        'echo "probe_data: $probe_data"',
        'echo "process_that_wrote: $process_that_wrote"',
        'echo "processes_by_id: $processes_by_id"',
    ]

    commands.extend(echo_commands)
    print(echo_commands)
    full_command = "sh -c '" + "; ".join(commands) + "'"
    subprocess.run(
        [
            "ssh",
            *dest.ssh_options,
            address,
            full_command,
        ],
        capture_output=True,
        check=True,
        text=True,
    )

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
