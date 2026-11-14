"""Persistent investigation imports, observed graphs, and append-only entity review."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.database import datasets, entities, feedback, observations, utc_now
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
async def dataset_graph(dataset_id: str, request: Request, limit: int = Query(300, ge=1, le=300)):
    with request.app.state.database.connect() as connection:
        if not connection.execute(select(datasets.c.id).where(datasets.c.id == dataset_id)).first():
            raise HTTPException(404, "Unknown dataset")
        all_nodes = (
            connection.execute(
                select(entities)
                .where(entities.c.dataset_id == dataset_id)
                .order_by(entities.c.kind, entities.c.id)
            )
            .mappings()
            .all()
        )
        nodes = [dict(row) for row in all_nodes[:limit]]
        visible = {node["id"] for node in nodes}
        edges = connection.execute(
            select(observations).where(
                observations.c.dataset_id == dataset_id,
                observations.c.source_id.in_(visible),
                observations.c.target_id.in_(visible),
            )
        ).mappings()
        return {
            "dataset_id": dataset_id,
            "nodes": nodes,
            "edges": [dict(e) for e in edges],
            "total_nodes": len(all_nodes),
            "hidden_nodes": len(all_nodes) - len(nodes),
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
