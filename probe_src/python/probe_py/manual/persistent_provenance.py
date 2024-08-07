from __future__ import annotations
import typing
import json
import datetime
import dataclasses
import pathlib
import xdg_base_dirs


@dataclasses.dataclass(frozen=True)
class Inode:
    host: int
    device_major: int
    device_minor: int
    inode: int

    def str_id(self) -> str:
        return f"{self.host:012x}-{self.device_major:04x}-{self.device_minor:04x}-{self.inode:016x}"


@dataclasses.dataclass(frozen=True)
class InodeVersion:
    inode: Inode

    # Usually, different versions of the inode will have different mtimes
    # But not always.
    # The file could be modified multiple times within the granularity of the system's mtime clock or the user could change the mtime
    mtime: int

    # Size is included to give a simple "pseudo-hash" of the content
    # Different size implies different content, but not necessarily the converse: same size does not necessarily imply same content.
    # Size serves as an inexpensive check of whether the previous attributes uniquely identify the same contents
    size: int

    # TODO: Handle the case where the user manually changes the mtime without changing the size.
    # We have no way to tell versions if the user resets the mtime of a new version to the mtime of a previous version.
    # Possible solutions:
    # - Wrap, intercept, and warn *utime* lib calls,
    # - Use an xattr, if the underlying FS supports it.
    #   Our xattr would be "true mtime" that we would maintain and can't be changed by normal tools.
    # - Cry.

    def str_id(self) -> str:
        return f"{self.inode.str_id()}-{self.mtime:016x}-{self.size:016x}"


@dataclasses.dataclass(frozen=True)
class InodeMetadataVersion:
    inode_version: InodeVersion
    stat_results: bytes


@dataclasses.dataclass(frozen=True)
class Process:
    input_inodes: frozenset[InodeVersion]
    input_inode_metadatas: frozenset[InodeMetadataVersion]
    output_inodes: frozenset[InodeVersion]
    output_inode_metadatas: frozenset[InodeMetadataVersion]
    time: datetime.datetime
    cmd: tuple[str, ...]
    pid: int
    env: tuple[tuple[str, str], ...]
    wd: pathlib.Path


PROBE_HOME = xdg_base_dirs.xdg_data_home() / "PROBE"
PROCESS_ID_THAT_WROTE_INODE_VERSION = PROBE_HOME / "process_id_that_wrote_inode_version"
PROCESSES_BY_ID = PROBE_HOME / "processes_by_id"


def get_prov_upstream(root_inode_version: InodeVersion) -> tuple[typing.Mapping[int, Process], typing.Mapping[InodeVersion, int | None]]:
    """
    This function answers: What do we need to reconstruct the provenance of root_inode_version on another host?

    The answer is a set of Process objects and a map of InodeVersion writes.
    """
    inode_version_queue = list[InodeVersion]()
    inode_version_queue.append(root_inode_version)

    # Stuff we need to transfer
    inode_version_writes = dict[InodeVersion, int | None]()
    process_closure = dict[int, Process]()

    while inode_version_queue:
        inode_version = inode_version_queue.pop()
        if inode_version not in inode_version_writes:
            process_id_path = PROCESS_ID_THAT_WROTE_INODE_VERSION / inode_version.str_id()
            if process_id_path.exists():
                process_id = json.loads(process_id_path.read_text())
                inode_version_writes[inode_version] = process_id
                if process_id not in process_closure:
                    process_path = PROCESSES_BY_ID / str(process_id)
                    assert process_path.exists()
                    process = json.loads(process_path.read_text())
                    process_closure[process_id] = process
            else:
                inode_version_writes[inode_version] = None
    return process_closure, inode_version_writes
