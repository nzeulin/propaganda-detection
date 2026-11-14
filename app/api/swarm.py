"""Independent CPU-only coordination jobs over immutable observations."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.contracts import JobRecord
from app.core.database import analyses, datasets, entities, observations
from app.swarm.engine import analyze_coordination

router = APIRouter(prefix="/api/v1")


class SwarmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str


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
        return await stage(
            "coordination",
            lambda: asyncio.to_thread(analyze_coordination, nodes, events),
            {"dataset_id": job["target_id"], "event_count": len(events)},
        )

    return handle


@router.post("/swarm/analyze", status_code=202, response_model=JobRecord)
async def submit_swarm(body: SwarmInput, request: Request):
    with request.app.state.database.connect() as connection:
        found = connection.execute(select(datasets.c.id).where(datasets.c.id == body.dataset_id)).first()
    if not found:
        raise HTTPException(404, "Unknown dataset")
    return request.app.state.jobs.submit("swarm", body.dataset_id, body.model_dump(), {"coordination": "v1"})


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
