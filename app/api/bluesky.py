"""Explicit, bounded public-feed collection through durable, cancellable jobs."""

import asyncio
from threading import Event

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app.api.contracts import JobRecord
from app.api.datasets import persist_dataset
from app.core.database import jobs
from app.core.ingestion import DatasetInput, canonical_id
from app.swarm.bluesky import COLLECTION_VERSION, CollectionError, collect_author_feeds, normalize_actor

router = APIRouter(prefix="/api/v1/bluesky")


class CollectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actors: list[str] = Field(min_length=1, max_length=10)
    per_actor: int = Field(default=50, ge=1, le=200, strict=True)

    @field_validator("actors")
    @classmethod
    def public_profiles(cls, values):
        return list(dict.fromkeys(normalize_actor(value) for value in values))


def collection_handler(state):
    async def handle(job, stage):
        cancellation = Event()
        worker = None

        async def collect():
            nonlocal worker
            worker = asyncio.create_task(asyncio.to_thread(
                collect_author_feeds, job["payload"]["actors"], job["payload"]["per_actor"],
                cancellation=cancellation,
            ))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancellation.set()
                # Keep the worker slot until an in-flight public request stops.
                await asyncio.gather(worker, return_exceptions=True)
                raise

        try:
            rows, provenance = await collect()
            if not rows:
                raise HTTPException(422, "No valid authored posts returned. Try another public profile; no synthetic fallback was used.")
            # Do not place complete original records in the public job trace as well.
            await stage("public_feed_collection", lambda: provenance["collection"], job["payload"], "Bluesky public API")
            name = f"Bluesky: {', '.join(job['payload']['actors'])[:90]} · {provenance['collection']['started_at_utc']}"
            dataset = persist_dataset(state.database, DatasetInput(name=name, rows=rows), bluesky=provenance)
            return {
                "dataset_id": dataset["id"], "name": dataset["name"], "rows": rows,
                "collection": provenance["collection"],
                "posts": {uri: {"source_post_url": source["source_post_url"],
                                "author_handle_at_collection": source["author_handle_at_collection"]}
                          for uri, source in provenance["posts"].items()},
            }
        except CollectionError as exc:
            raise HTTPException(502, str(exc)) from exc
        finally:
            cancellation.set()

    return handle


@router.post("/collect", status_code=202, response_model=JobRecord)
async def collect_public_profiles(body: CollectionInput, request: Request):
    state = request.app.state
    with state.database.connect() as connection:
        count = connection.execute(select(func.count()).select_from(jobs).where(
            jobs.c.kind == "bluesky", jobs.c.status.in_(["queued", "running"]),
        )).scalar_one()
    if count >= 4:
        raise HTTPException(429, "Public collection queue is full. Wait for a running collection; no automatic retry.")
    payload = body.model_dump()
    return state.jobs.submit("bluesky", canonical_id("bluesky-collection", payload), payload,
                             {"bluesky": COLLECTION_VERSION})