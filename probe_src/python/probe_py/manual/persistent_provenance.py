from __future__ import annotations
import typing
import os
import random
import socket
import json
import datetime
import dataclasses
import pathlib
import xdg_base_dirs


PROBE_HOME = xdg_base_dirs.xdg_data_home() / "PROBE"
PROCESS_ID_THAT_WROTE_INODE_VERSION = PROBE_HOME / "process_id_that_wrote_inode_version"
PROCESSES_BY_ID = PROBE_HOME / "processes_by_id"


# Also note: https://news.ycombinator.com/item?id=25544397
#
# >>> I found that performance is pretty decent if you do almost everything inside SQLite using WITH RECURSIVE.
#
# >> The issue I found with WITH RECURSIVE queries is that they're incredibly inefficient for anything but trees. I've looked around and there doesn't seem to be any way to store a global list of visited nodes. This means that when performing a traversal of the graph the recursive query will follow all paths between two nodes.
#
# > I would say they are reasonably efficient.
# > Of course many orders of magnitude slower than keeping it all in in memory maps and doing the traversal there, but fast enough to not be a limiting factor.
# > Traversing a medium depth DAG with a million nodes to find orphaned nodes takes less than a second on average hardware.
# > One thing to be aware of is that SQLite has lots of tuning options, and they are all set to very conservative values by default.
# > E.g. the default journal mode is FULL, which means that it will flush all the way to disk after each write. The default cache size is tiny.
# > With a bit of tuning you can get quite decent performance out of SQLite while still having full ACID guarantees, or very good performance for cases where you can compromise on the ACID stuff.


def get_local_node_name() -> str:
    node_name = PROBE_HOME / "node_name"
    if node_name.exists():
        return node_name.read_text()
    else:
        hostname = socket.gethostname()
        rng = random.Random(int(datetime.datetime.now().timestamp()) ^ hash(hostname))
        bits_per_hex_digit = 4
        hex_digits = 8
        random_number = rng.getrandbits(bits_per_hex_digit * hex_digits)
        node_name = f"{random_number:0{hex_digits}x}.{hostname}"
        file_path = pathlib.Path(node_name)
        file_path.write_text(node_name)
        return node_name


@dataclasses.dataclass(frozen=True)
class Inode:
    host: str
    device_major: int
    device_minor: int
    inode: int

    def to_dict(self):
        return {
            'host': self.host,
            'device_major': self.device_major,
            'device_minor': self.device_minor,
            'inode': self.inode,
        }

    def str_id(self) -> str:
        hex_part = self.host.split('.')[0]
        if hex_part:
            number = int(hex_part, 16)
        else:
            number = 0
        return f"{number:012x}-{self.device_major:04x}-{self.device_minor:04x}-{self.inode:016x}"

    @staticmethod
    def from_local_path(path: pathlib.Path, stat_info: os.StatResult | None = None) -> Inode:
        if stat_info is None:
            stat_info = os.stat(path)
        device_major = os.major(stat_info.st_dev)
        device_minor = os.minor(stat_info.st_dev)
        inode_val = stat_info.st_ino
        host = get_local_node_name()
        return Inode(host, device_major, device_minor, inode_val)


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

    def to_dict(self):
        data = {"mtime": self.mtime, 'inode': self.inode.to_dict(), "size": self.size}
        return data

    def str_id(self) -> str:
        return f"{self.inode.str_id()}-{self.mtime:016x}-{self.size:016x}"

    @staticmethod
    def from_local_path(path: pathlib.Path, stat_info: os.StatInfo) -> InodeVersion:
        if stat_info is None:
            stat_info = os.stat(path)
        mtime = int(stat_info.st_mtime * 1_000_000_000)
        size = stat_info.st_size
        return InodeVersion(Inode.from_local_path(path, stat_info), mtime, size)


@dataclasses.dataclass(frozen=True)
class InodeMetadata:
    inode: Inode
    mode: int
    nlink: int
    uid: int
    gid: int

    def to_dict(self):
        return {
            "inode": self.inode.to_dict(),
            "mode": self.mode,
            "nlink": self.nlink,
            "uid": self.uid,
            "gid": self.gid,
        }

    @staticmethod
    def from_local_path(path: pathlib.Path, stat_info: os.StatInfo) -> InodeMetadata:
        if stat_info is None:
            stat_info = os.stat(path)
        return InodeMetadata(
            Inode.from_local_path(path, stat_info),
            mode=stat_info.st_mode,
            nlink=stat_info.st_nlink,
            uid=stat_info.st_uid,
            gid=stat_info.st_gid,
        )


@dataclasses.dataclass(frozen=True)
class Process:
    input_inodes: frozenset[InodeVersion]
    input_inode_metadatas: frozenset[InodeMetadata]
    output_inodes: frozenset[InodeVersion]
    output_inode_metadatas: frozenset[InodeMetadata]
    time: datetime.datetime
    cmd: tuple[str, ...]
    pid: int
    env: tuple[tuple[str, str], ...]
    wd: pathlib.Path

    def to_dict(self):
        return {
            'input_inodes': [inode_version.to_dict() for inode_version in self.input_inodes],
            'input_inode_metadatas': [metadata.to_dict() for metadata in self.input_inode_metadatas],
            'output_inodes': [inode_version.to_dict() for inode_version in self.output_inodes],
            'output_inode_metadatas': [metadata.to_dict() for metadata in self.output_inode_metadatas],
            'time': self.time.isoformat(),
            'cmd': list(self.cmd),
            'pid': self.pid,
            'env': [tuple(env_item) for env_item in self.env],
            'wd': str(self.wd),
        }


# TODO: implement this for remote host
def get_prov_upstream(
        root_inode_version: list[InodeVersion],
        host: str,
) -> tuple[typing.Mapping[int, Process], typing.Mapping[InodeVersion, int | None]]:
    """
    This function answers: What do we need to reconstruct the provenance of root_inode_version on another host?
    The answer is a set of Process objects and a map of InodeVersion writes.
    """
    if host != "local":
        raise NotImplementedError("scp where source is remote is not implemented, because it would be hard to copy the remote prov")
    inode_version_queue = list[InodeVersion]()
    inode_version_queue.extend(root_inode_version)

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
