import time
import os
import getpass
import grp
import pathlib
import tarfile
import typing


def get_umask() -> int:
    old_umask = os.umask(0o644)
    os.umask(old_umask)
    return old_umask


def default_tarinfo(path: pathlib.Path | str) -> tarfile.TarInfo:
    return tarfile.TarInfo(name=str(path)).replace(
        mtime=int(time.time()),
        mode=get_umask(),
        uid=os.getuid(),
        gid=os.getgid(),
        uname=getpass.getuser(),
        gname=grp.getgrgid(os.getgid()).gr_name,
    )


def filter_relative_to(path: pathlib.Path) -> typing.Callable[[tarfile.TarInfo], tarfile.TarInfo]:
    def filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
        member_path = pathlib.Path(member.name)
        return member.replace(name=str(member_path.relative_to(path)))
    return filter
