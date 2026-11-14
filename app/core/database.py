"""Local investigation storage with explicit schema revision and atomic transactions."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    text,
)

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
    Column("analysis_id", ForeignKey("analyses.id")),
)
jobs = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, nullable=False),
    Column("target_id", String, nullable=False, index=True),
    Column("fingerprint", String, nullable=False, index=True),
    Column("status", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("trace", JSON, nullable=False),
    Column("result", JSON),
    Column("error", JSON),
)
analyses = Table(
    "analyses",
    metadata,
    Column("id", String, primary_key=True),
    Column("job_id", ForeignKey("jobs.id"), nullable=False, unique=True),
    Column("target_id", String, nullable=False, index=True),
    Column("kind", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("result", JSON, nullable=False),
)

embedding_cache = Table(
    "embedding_cache", metadata,
    Column("id", String, primary_key=True),
    Column("model", String, nullable=False),
    Column("dimensions", Integer, nullable=False),
    Column("vector", JSON, nullable=False),
    Column("created_at", String, nullable=False),
)
agent_pairs = Table(
    "agent_pairs", metadata,
    Column("job_id", ForeignKey("jobs.id"), primary_key=True),
    Column("id", String, primary_key=True),
    Column("source_id", ForeignKey("entities.id"), nullable=False),
    Column("target_id", ForeignKey("entities.id"), nullable=False),
    Column("mention", Boolean, nullable=False),
    Column("similarity", Float, nullable=False),
    Column("score", Float, nullable=False),
    Column("weight", Float, nullable=False),
    Column("evidence", JSON, nullable=False),
)
Index("agent_pairs_score", agent_pairs.c.job_id, agent_pairs.c.score)


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
        revisions.create(connection, checkfirst=True)
        version = connection.execute(revisions.select()).scalar()
        if version not in (None, 1, 2, 3, 4):
            raise RuntimeError(f"Unsupported database schema revision {version}; migration required.")
        # Revision 4 adds derived connectivity/cache tables without changing source records.
        metadata.create_all(connection)
        if version in (1, 2):
            connection.execute(
                text("ALTER TABLE feedback ADD COLUMN analysis_id VARCHAR REFERENCES analyses(id)")
            )
        connection.execute(revisions.delete())
        connection.execute(revisions.insert().values(version=4))
    return engine
