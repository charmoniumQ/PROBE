from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, PrimaryKeyConstraint
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import xdg_base_dirs
import pathlib

class Base(DeclarativeBase):
    pass

_engine = None
def get_engine():
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
    id = Column(Integer, primary_key=True, autoincrement=True)
    inode = Column(Integer)
    process_id = Column(Integer)
    device_major = Column(Integer)
    device_minor = Column(Integer)
    host = Column(Integer)
    path = Column(String)
    mtime = Column(Integer)
    size = Column(Integer)


class Process(Base):
    __tablename__ = 'process'

    process_id = Column(Integer, primary_key=True)
    parent_process_id = Column(Integer, nullable=True)
    cmd = Column(String)
    time = Column(TIMESTAMP)


class ProcessInputs(Base):
    __tablename__ = 'process_inputs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    inode = Column(Integer)
    process_id = Column(Integer)
    device_major = Column(Integer)
    device_minor = Column(Integer)
    host = Column(Integer)
    path = Column(String)
    mtime = Column(Integer)
    size = Column(Integer)

print("Tables for persistent provenance created successfully.")