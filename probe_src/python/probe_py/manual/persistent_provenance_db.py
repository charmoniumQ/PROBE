from sqlalchemy import create_engine, DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy.engine import Engine
import xdg_base_dirs
import pathlib
from datetime import datetime

class Base(DeclarativeBase):
    pass

_engine = None
def get_engine()->Engine:
    global _engine
    if _engine is None:
        home = pathlib.Path(xdg_base_dirs.xdg_data_home())
        home.mkdir(parents=True, exist_ok=True)
        database_path = home / "probe_log.db"

        _engine = create_engine(f'sqlite:///{database_path}', echo=True)
        Base.metadata.create_all(_engine)
    return _engine

class ProcessThatWrites(Base):
    __tablename__ = 'process_that_writes'

    id: Mapped[int] = mapped_column(primary_key=True, auto_increment=True)
    inode: Mapped[int]
    process_id: Mapped[int]
    device_major: Mapped[int]
    device_minor: Mapped[int]
    host: Mapped[int]
    path: Mapped[str]
    mtime: Mapped[int]
    size: Mapped[int]


class Process(Base):
    __tablename__ = 'process'

    process_id: Mapped[int] = mapped_column(primary_key=True)
    parent_process_id: Mapped[int]
    cmd: Mapped[str]
    time: Mapped[datetime] = mapped_column(DateTime)


class ProcessInputs(Base):
    __tablename__ = 'process_inputs'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inode: Mapped[int]
    process_id: Mapped[int]
    device_major: Mapped[int]
    device_minor: Mapped[int]
    host: Mapped[int]
    path: Mapped[str]
    mtime: Mapped[int]
    size: Mapped[int]

print("Tables for persistent provenance created successfully.")