"""Independent CPU-only coordination jobs over immutable observations."""

import asyncio
from threading import Event

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.contracts import JobRecord
from app.core.database import analyses, datasets, entities, observations
from app.swarm.engine import VERSION, analyze_coordination
from app.swarm.examples import swarm_examples

router = APIRouter(prefix="/api/v1")


class SwarmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str = Field(min_length=1, max_length=200)


@router.get("/swarm/examples")
async def examples():
    """Return input observations, never precomputed detector verdicts."""
    return swarm_examples()


def swarm_handler(state):
    async def handle(job, stage):
        with state.database.connect() as connection:
            nodes = [
                dict(r)
                for r in connection.execute(
                    select(entities).where(entities.c.dataset_id == job["target_id"])
                ).mappings()
            ]
            events = [
                dict(r)
                for r in connection.execute(
                    select(observations).where(observations.c.dataset_id == job["target_id"])
                ).mappings()
            ]
        cancellation = Event()
        try:
            return await stage(
                "coordination",
                lambda: asyncio.to_thread(analyze_coordination, nodes, events, cancellation=cancellation),
                {"dataset_id": job["target_id"], "event_count": len(events)},
            )
        finally:
            cancellation.set()

    return handle


@router.post("/swarm/analyze", status_code=202, response_model=JobRecord)
async def submit_swarm(body: SwarmInput, request: Request):
    with request.app.state.database.connect() as connection:
        found = connection.execute(select(datasets.c.id).where(datasets.c.id == body.dataset_id)).first()
    if not found:
        raise HTTPException(404, "Unknown dataset")
    return request.app.state.jobs.submit("swarm", body.dataset_id, body.model_dump(), {"coordination": VERSION})


@router.get("/swarm/{dataset_id}/analysis")
async def swarm_analysis(dataset_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        record = (
            connection.execute(
                select(analyses)
                .where(analyses.c.kind == "swarm", analyses.c.target_id == dataset_id)
                .order_by(analyses.c.created_at.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
    if not record:
        raise HTTPException(404, "No saved coordination analysis")
    return dict(record)
