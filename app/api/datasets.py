"""Persistent investigation imports, observed graphs, and append-only entity review."""

from collections import deque
from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.agent_connectivity import connectivity_record
from app.content.screening import scoring_signature, with_post_screening
from app.core.database import agent_pairs, analyses, datasets, entities, feedback, jobs, observations, utc_now
from app.core.ingestion import DatasetInput, prepare_dataset
from app.core.interactions import observed_graph

router = APIRouter(prefix="/api/v1")


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    decision: Literal["confirm", "dismiss", "needs_review"]
    reason: str = Field(default="", max_length=4000)
    analysis_id: str | None = None


def persist_dataset(database, body: DatasetInput, *, bluesky=None):
    """Atomically persist an import; optional source metadata is server-collected only."""
    try:
        dataset_id, source, nodes, events = prepare_dataset(body)
    except ValueError as exc:
        raise HTTPException(422, detail=exc.args[0]) from exc
    if bluesky is not None:
        source["bluesky"] = bluesky
        accounts = {a["did"]: a["handle"] for a in bluesky["collection"]["accounts"] if "handle" in a}
        content_ids = {node["data"]["source_id"]: node["id"] for node in nodes if node["kind"] == "content"}
        interactions = {
            (item["account_id"], item["content_id"], item["action"], item.get("timestamp")): item
            for item in bluesky.get("interactions", [])
        }
        origins = {}
        for item in interactions.values():
            origins.setdefault(item["account_id"], []).append({
                "seed_post_id": item["content_id"], "action": item["action"],
            })
        for node in nodes:
            if node["kind"] == "account":
                node["data"]["handle"] = accounts.get(node["data"]["source_id"])
                if node["data"]["source_id"] in origins:
                    node["data"]["discovery_origins"] = origins[node["data"]["source_id"]]
            elif node["kind"] == "content":
                original = bluesky["posts"].get(node["data"]["source_id"], {})
                node["data"]["source_post_url"] = original.get("source_post_url")
                record = original.get("original_record", {})
                reply = record.get("reply", {})
                parent = reply.get("parent", {}) if isinstance(reply, dict) else {}
                embed = record.get("embed", {})
                quoted = embed.get("record", {}) if isinstance(embed, dict) else {}
                if isinstance(quoted, dict) and "record" in quoted:
                    quoted = quoted["record"]
                for field, target in (("reply_to_content_id", parent), ("quote_to_content_id", quoted)):
                    if isinstance(target, dict) and target.get("uri") in content_ids:
                        node["data"][field] = target["uri"]
                if original.get("discovery_origins"):
                    node["data"]["discovery_origins"] = original["discovery_origins"]
        for event in events:
            row = event["data"].get("normalized", {})
            evidence = interactions.get((row.get("account_id"), row.get("content_id"),
                                         row.get("action"), row.get("timestamp")))
            if evidence:
                response = content_ids.get(evidence.get("response_content_id"))
                event["data"]["response_content_id"] = response
                if event["action"] == "replied_to":
                    event["data"]["reply_content_id"] = response
                event["data"]["source_post_url"] = bluesky["posts"].get(
                    evidence.get("response_content_id"), {}
                ).get("source_post_url")
    with database.begin() as connection:
        existing = connection.execute(select(datasets).where(datasets.c.id == dataset_id)).mappings().first()
        if existing:
            return dict(existing)
        record = {"id": dataset_id, "name": body.name, "created_at": utc_now(), "source": source}
        connection.execute(datasets.insert(), record)
        connection.execute(entities.insert(), nodes)
        connection.execute(observations.insert(), events)
    return record


@router.post("/datasets", status_code=201)
async def import_dataset(body: DatasetInput, request: Request):
    return persist_dataset(request.app.state.database, body)


@router.get("/datasets/{dataset_id}/provenance")
async def dataset_provenance(dataset_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        record = connection.execute(select(datasets.c.source).where(datasets.c.id == dataset_id)).first()
    if not record:
        raise HTTPException(404, "Unknown dataset")
    provenance = record[0].get("bluesky")
    if not provenance:
        raise HTTPException(404, "This dataset has no server-collected Bluesky provenance")
    return provenance


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


@router.get("/datasets/{dataset_id}/activity")
async def entity_activity(
    dataset_id: str, request: Request, entity_id: str,
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
):
    """Inspect saved actions and response material beyond the graph's display cap."""
    with request.app.state.database.connect() as connection:
        nodes = {row["id"]: dict(row) for row in connection.execute(select(entities).where(
            entities.c.dataset_id == dataset_id
        )).mappings()}
        if entity_id not in nodes:
            raise HTTPException(404, "Unknown entity for this dataset")
        events = [dict(row) for row in connection.execute(select(observations).where(
            observations.c.dataset_id == dataset_id
        )).mappings()]
    _, events = observed_graph(nodes.values(), events)
    related = [event for event in events if entity_id in (
        event["source_id"], event["target_id"], event["data"].get("response_content_id"),
    )]
    related.sort(key=lambda event: (event.get("timestamp") or "", event["id"]), reverse=True)
    return {
        "entity": nodes[entity_id], "total": len(related), "offset": offset, "limit": limit,
        "items": [{**event, "account": nodes[event["source_id"]], "content": nodes[event["target_id"]],
                   "response": nodes.get(event["data"].get("response_content_id"))}
                  for event in related[offset:offset + limit]],
    }


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
    connectivity_analysis_id: str | None = None,
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
        connectivity = None
        connectivity_edges = []
        if connectivity_analysis_id:
            connectivity = connectivity_record(connection, connectivity_analysis_id, dataset_id)
            connectivity_edges = [dict(row) for row in connection.execute(select(
                *(agent_pairs.c[key] for key in ("id", "source_id", "target_id", "mention", "similarity", "score", "weight"))
            ).where(
                agent_pairs.c.job_id == connectivity["job_id"], agent_pairs.c.weight > 0
            )).mappings()]
        content_screenings = {}
        saved = connection.execute(
            select(
                jobs.c.target_id,
                jobs.c.id,
                jobs.c.result["analysis_id"].label("analysis_id"),
                jobs.c.result["features"].label("features"),
            )
            .select_from(jobs.join(entities, jobs.c.target_id == entities.c.id))
            .where(
                entities.c.dataset_id == dataset_id,
                entities.c.kind == "content",
                jobs.c.kind == "content",
                jobs.c.status == "completed",
                jobs.c.payload["verification"].as_string() == "none",
                jobs.c.payload["scoring_signature"].as_string() == scoring_signature(request.app.state.config),
            )
            .order_by(jobs.c.created_at.desc(), jobs.c.id)
        ).mappings()
        for score in saved:
            current = with_post_screening({"features": score["features"]}, request.app.state.config)
            content_screenings.setdefault(score["target_id"], {
                "job_id": score["id"],
                "analysis_id": score["analysis_id"],
                "features": current["features"],
                "screening": current["propaganda_screening"],
            })
    eligible, edges = observed_graph(nodes.values(), edges)
    nodes = {node["id"]: node for node in eligible}
    if since or until:
        edges = [
            e
            for e in edges
            if e["timestamp"]
            and (not since or datetime.fromisoformat(e["timestamp"]) >= since)
            and (not until or datetime.fromisoformat(e["timestamp"]) <= until)
        ]
    clusters = [
        {**group, "account_ids": [agent for agent in group["account_ids"] if agent in nodes]}
        for group in (connectivity["result"]["clusters"] if connectivity else swarm["clusters"] if swarm else [])
    ]
    clusters = [group for group in clusters if len(group["account_ids"]) >= (2 if connectivity else 3)]
    adjacency = {node: set() for node in nodes}
    for edge in edges:
        adjacency[edge["source_id"]].add(edge["target_id"])
        adjacency[edge["target_id"]].add(edge["source_id"])
    for edge in connectivity_edges:
        if edge["source_id"] in nodes and edge["target_id"] in nodes:
            adjacency[edge["source_id"]].add(edge["target_id"])
            adjacency[edge["target_id"]].add(edge["source_id"])
    if focus:
        seeds = [focus] if focus in nodes and (not (since or until) or adjacency[focus]) else []
    elif cluster:
        seeds = next((c["account_ids"] for c in clusters if c["id"] == cluster), [])
        seeds = [node for node in seeds if not (since or until) or adjacency[node]]
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
    result = {
        "dataset_id": dataset_id,
        "nodes": [nodes[n] for n in selected],
        "edges": [e for e in edges if e["source_id"] in visible and e["target_id"] in visible],
        "clusters": clusters,
        "total_nodes": len(nodes),
        "hidden_nodes": len(nodes) - len(selected),
        "time_filter_excludes_unknown": bool(since or until),
        "content_screenings": content_screenings,
    }
    if connectivity:
        result.update({
            "connectivity_analysis_id": connectivity_analysis_id,
            "connectivity_scope": "full_dataset",
            "connectivity_edges": [
                edge for edge in connectivity_edges if edge["source_id"] in visible and edge["target_id"] in visible
            ],
        })
    return result


@router.post("/feedback", status_code=201)
async def review_entity(body: ReviewInput, request: Request):
    with request.app.state.database.begin() as connection:
        entity = (
            connection.execute(select(entities).where(entities.c.id == body.target_id)).mappings().first()
        )
        if not entity:
            raise HTTPException(404, "Unknown review target")
        if body.analysis_id:
            analysis = (
                connection.execute(select(analyses).where(analyses.c.id == body.analysis_id))
                .mappings()
                .first()
            )
            if not analysis or analysis["target_id"] not in (body.target_id, entity["dataset_id"]):
                raise HTTPException(
                    422, "Analysis revision does not belong to the reviewed entity or dataset"
                )
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
