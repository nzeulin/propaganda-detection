"""Local investigation storage with explicit schema revision and atomic transactions."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON, Column, ForeignKey, Integer, MetaData, String, Table, create_engine, event

metadata = MetaData()
revisions = Table("schema_revisions", metadata, Column("version", Integer, primary_key=True))
datasets = Table(
    "datasets",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("source", JSON, nullable=False),
)
entities = Table(
    "entities",
    metadata,
    Column("id", String, primary_key=True),
    Column("dataset_id", ForeignKey("datasets.id"), nullable=False, index=True),
    Column("kind", String, nullable=False),
    Column("data", JSON, nullable=False),
)
observations = Table(
    "observations",
    metadata,
    Column("id", String, primary_key=True),
    Column("dataset_id", ForeignKey("datasets.id"), nullable=False, index=True),
    Column("source_id", ForeignKey("entities.id"), nullable=False),
    Column("target_id", ForeignKey("entities.id"), nullable=False),
    Column("action", String, nullable=False),
    Column("timestamp", String),
    Column("data", JSON, nullable=False),
)
feedback = Table(
    "feedback",
    metadata,
    Column("id", String, primary_key=True),
    Column("target_id", ForeignKey("entities.id"), nullable=False, index=True),
    Column("decision", String, nullable=False),
    Column("reason", String, nullable=False),
    Column("created_at", String, nullable=False),
)


def utc_now():
    return datetime.now(UTC).isoformat()


def open_database(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    with engine.begin() as connection:
        metadata.create_all(connection)
        version = connection.execute(revisions.select()).scalar()
        if version is None:
            connection.execute(revisions.insert().values(version=1))
        elif version != 1:
            raise RuntimeError(f"Unsupported database schema revision {version}; migration required.")
    return engine
