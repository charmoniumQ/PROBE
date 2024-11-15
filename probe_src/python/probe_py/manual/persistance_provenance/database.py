from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///process_database.db', echo=True)
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

    id = Column(Integer, primary_key=True)
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

print("Tables created successfully.")
