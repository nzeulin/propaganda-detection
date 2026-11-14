"""Agent connectivity and legacy temporal jobs over immutable observations."""

import asyncio
from threading import Event
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.contracts import JobRecord
from app.core.database import analyses, datasets, entities, observations
from app.swarm.connectivity import prepare_agents
from app.swarm.engine import VERSION, analyze_coordination
from app.swarm.examples import swarm_examples

router = APIRouter(prefix="/api/v1")


class SwarmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str = Field(min_length=1, max_length=200)
    mode: Literal["temporal", "agent_connectivity"] = "temporal"
    connectivity_threshold: float = Field(default=0.25, ge=0, lt=2)


@router.get("/swarm/examples")
async def examples():
    """Return input observations, never precomputed detector verdicts."""
    return swarm_examples()


def swarm_handler(state):
    async def handle(job, stage):
        with state.database.connect() as connection:
            source = connection.execute(select(datasets.c.source).where(datasets.c.id == job["target_id"])).scalar_one()
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
            result = await stage(
                "coordination",
                lambda: asyncio.to_thread(analyze_coordination, nodes, events, cancellation=cancellation),
                {"dataset_id": job["target_id"], "event_count": len(events)},
            )
            provenance = source.get("bluesky")
            if provenance:
                result["collection"] = provenance["collection"]
                handles = {a["did"]: "@" + a["handle"] for a in provenance["collection"]["accounts"] if "handle" in a}
                result["account_labels"] = {key: handles.get(label, label) for key, label in result["account_labels"].items()}
                for finding in result["findings"]:
                    for episode in finding["episodes"]:
                        for event in episode["matched_events"]:
                            event["account_label"] = result["account_labels"].get(event["account_id"], event["account_label"])
                            event["source_post_url"] = provenance["posts"].get(event["content_label"], {}).get("source_post_url")
            return result
        finally:
            cancellation.set()

    return handle


@router.post("/swarm/analyze", status_code=202, response_model=JobRecord)
async def submit_swarm(body: SwarmInput, request: Request):
    with request.app.state.database.connect() as connection:
        found = connection.execute(select(datasets.c.id).where(datasets.c.id == body.dataset_id)).first()
    if not found:
        raise HTTPException(404, "Unknown dataset")
    state = request.app.state
    if body.mode == "agent_connectivity":
        if state.agent_embedder is None:
            raise HTTPException(503, "Agent connectivity requires a configured OPENAI_API_KEY.")
        with state.database.connect() as connection:
            nodes = [dict(row) for row in connection.execute(select(entities).where(
                entities.c.dataset_id == body.dataset_id
            )).mappings()]
            events = [dict(row) for row in connection.execute(select(observations).where(
                observations.c.dataset_id == body.dataset_id
            )).mappings()]
        try:
            prepare_agents(nodes, events, state.agent_embedder.policy)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return state.jobs.submit("agent_connectivity", body.dataset_id, body.model_dump(), state.agent_embedder.policy)
    return state.jobs.submit("swarm", body.dataset_id, {"dataset_id": body.dataset_id}, {"coordination": VERSION})


@router.get("/swarm/{dataset_id}/analysis")
async def swarm_analysis(dataset_id: str, request: Request, mode: Literal["temporal", "agent_connectivity"] = "temporal"):
    with request.app.state.database.connect() as connection:
        record = (
            connection.execute(
                select(analyses)
                .where(analyses.c.kind == ("swarm" if mode == "temporal" else mode), analyses.c.target_id == dataset_id)
                .order_by(analyses.c.created_at.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
    if not record:
        raise HTTPException(404, "No saved coordination analysis")
    return dict(record)
