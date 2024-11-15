from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import xdg_base_dirs

database_path = xdg_base_dirs.xdg_data_home() / "probe_log.db"
engine = create_engine(f'sqlite:///{database_path}', echo=True)
Base = declarative_base()


class ProcessThatWrites(Base):
    __tablename__ = 'process_that_writes'

    inode = Column(Integer)
    process_id = Column(Integer)
    device_major = Column(Integer)
    device_minor = Column(Integer)
    host = Column(String)
    path = Column(String)

    __table_args__ = (
        PrimaryKeyConstraint('inode', 'process_id'),  # Composite primary key
    )


class Process(Base):
    __tablename__ = 'process'

    process_id = Column(Integer, primary_key=True)
    parent_process_id = Column(Integer, nullable=True)
    cmd = Column(String)
    time = Column(TIMESTAMP)


class ProcessInputs(Base):
    __tablename__ = 'process_inputs'

    inode = Column(Integer)
    process_id = Column(Integer)
    device_major = Column(Integer)
    device_minor = Column(Integer)
    host = Column(String)
    path = Column(String)

    __table_args__ = (
        PrimaryKeyConstraint('inode', 'process_id'),
    )


Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

print("Tables for persistent provenance created successfully.")