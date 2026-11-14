"""Persistent investigation imports, observed graphs, and append-only entity review."""

from collections import deque
from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.database import analyses, datasets, entities, feedback, observations, utc_now
from app.core.ingestion import DatasetInput, prepare_dataset

router = APIRouter(prefix="/api/v1")


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    decision: Literal["confirm", "dismiss", "needs_review"]
    reason: str = Field(default="", max_length=4000)


@router.post("/datasets", status_code=201)
async def import_dataset(body: DatasetInput, request: Request):
    try:
        dataset_id, source, nodes, events = prepare_dataset(body)
    except ValueError as exc:
        raise HTTPException(422, detail=exc.args[0]) from exc
    with request.app.state.database.begin() as connection:
        existing = connection.execute(select(datasets).where(datasets.c.id == dataset_id)).mappings().first()
        if existing:
            return dict(existing)
        record = {"id": dataset_id, "name": body.name, "created_at": utc_now(), "source": source}
        connection.execute(datasets.insert(), record)
        connection.execute(entities.insert(), nodes)
        connection.execute(observations.insert(), events)
    return record


@router.get("/datasets")
async def list_datasets(request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    with request.app.state.database.connect() as connection:
        records = connection.execute(
            select(datasets.c.id, datasets.c.name, datasets.c.created_at)
            .order_by(datasets.c.created_at.desc(), datasets.c.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [dict(record) for record in records]


@router.get("/datasets/{dataset_id}/graph")
async def dataset_graph(
    dataset_id: str,
    request: Request,
    limit: int = Query(300, ge=1, le=300),
    search: str = "",
    focus: str | None = None,
    cluster: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
):
    if any(value and value.tzinfo is None for value in (since, until)):
        raise HTTPException(422, "Time filters require a UTC offset")
    with request.app.state.database.connect() as connection:
        if not connection.execute(select(datasets.c.id).where(datasets.c.id == dataset_id)).first():
            raise HTTPException(404, "Unknown dataset")
        nodes = {
            r["id"]: dict(r)
            for r in connection.execute(
                select(entities).where(entities.c.dataset_id == dataset_id)
            ).mappings()
        }
        edges = [
            dict(r)
            for r in connection.execute(
                select(observations).where(observations.c.dataset_id == dataset_id)
            ).mappings()
        ]
        swarm = connection.execute(
            select(analyses.c.result)
            .where(analyses.c.target_id == dataset_id, analyses.c.kind == "swarm")
            .order_by(analyses.c.created_at.desc())
            .limit(1)
        ).scalar()
    if since or until:
        edges = [
            e
            for e in edges
            if e["timestamp"]
            and (not since or datetime.fromisoformat(e["timestamp"]) >= since)
            and (not until or datetime.fromisoformat(e["timestamp"]) <= until)
        ]
    clusters = swarm["clusters"] if swarm else []
    inferred = [f for f in swarm["findings"] if f["strong"]] if swarm and not (since or until) else []
    edges.extend(inferred)
    adjacency = {node: set() for node in nodes}
    for edge in edges:
        adjacency[edge["source_id"]].add(edge["target_id"])
        adjacency[edge["target_id"]].add(edge["source_id"])
    if focus:
        seeds = [focus] if focus in nodes else []
    elif cluster:
        seeds = next((c["account_ids"] for c in clusters if c["id"] == cluster), [])
    else:
        seeds = [
            node_id
            for node_id, n in nodes.items()
            if search.casefold() in str(n["data"]).casefold() and (not (since or until) or adjacency[node_id])
        ]
    selected, pending = [], deque(seeds if focus or cluster else seeds[:1])
    seen = set()
    # Traverse observed neighborhoods first so the cap cannot produce 300 isolated accounts.
    while len(selected) < limit and (pending or seeds):
        if not pending:
            pending.append(seeds.pop(0))
        node_id = pending.popleft()
        if node_id in seen:
            continue
        seen.add(node_id)
        selected.append(node_id)
        pending.extend(sorted(adjacency[node_id] - seen))
    visible = set(selected)
    return {
        "dataset_id": dataset_id,
        "nodes": [nodes[n] for n in selected],
        "edges": [e for e in edges if e["source_id"] in visible and e["target_id"] in visible],
        "clusters": clusters,
        "total_nodes": len(nodes),
        "hidden_nodes": len(nodes) - len(selected),
        "time_filter_excludes_unknown": bool(since or until),
    }


@router.post("/feedback", status_code=201)
async def review_entity(body: ReviewInput, request: Request):
    with request.app.state.database.begin() as connection:
        if not connection.execute(select(entities.c.id).where(entities.c.id == body.target_id)).first():
            raise HTTPException(404, "Unknown review target")
        record = {"id": str(uuid4()), **body.model_dump(), "created_at": utc_now()}
        connection.execute(feedback.insert(), record)
    return record


@router.get("/feedback")
async def review_history(request: Request, target_id: str, limit: int = Query(100, ge=1, le=100)):
    with request.app.state.database.connect() as connection:
        records = connection.execute(
            select(feedback)
            .where(feedback.c.target_id == target_id)
            .order_by(feedback.c.created_at.desc(), feedback.c.id)
            .limit(limit)
        ).mappings()
        return [dict(record) for record in records]
