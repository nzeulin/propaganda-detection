"""Versioned connectivity jobs and paginated evidence; reads never invoke a model."""

import asyncio
from threading import Event

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, or_, select

from app.core.database import agent_pairs, analyses, datasets, entities, observations
from app.swarm.connectivity import collect_mentions, compute_connectivity, prepare_agents

router = APIRouter(prefix="/api/v1/agent-connectivity", tags=["Agent connectivity"])


def connectivity_record(connection, analysis_id, dataset_id=None):
    record = connection.execute(select(analyses).where(
        analyses.c.id == analysis_id, analyses.c.kind == "agent_connectivity",
    )).mappings().first()
    if record is None or (dataset_id is not None and record["target_id"] != dataset_id):
        raise HTTPException(404, "Unknown completed connectivity analysis for this dataset")
    return record


def connectivity_handler(state):
    async def handle(job, stage):
        with state.database.connect() as connection:
            source = connection.execute(select(datasets.c.source).where(
                datasets.c.id == job["target_id"]
            )).scalar_one()
            nodes = [dict(row) for row in connection.execute(select(entities).where(
                entities.c.dataset_id == job["target_id"]
            )).mappings()]
            events = [dict(row) for row in connection.execute(select(observations).where(
                observations.c.dataset_id == job["target_id"]
            )).mappings()]
        provider = state.agent_embedder
        agents, materials = prepare_agents(nodes, events, provider.policy)
        cancellation = Event()
        try:
            mentions = await stage("mentions", lambda: asyncio.to_thread(
                collect_mentions, agents, materials, source
            ))
            # Stage artifacts contain cache references and counts, never raw vectors.
            embedding_info = await stage("embeddings", lambda: provider.embed_materials(
                state.database, {key: value["data"]["text"] for key, value in materials.items()}
            ), {"materials": len(materials)}, provider=provider.policy["model"])
            result = await stage("agent_connectivity", lambda: asyncio.to_thread(
                compute_connectivity, state.database, job, agents, materials, embedding_info,
                mentions, job["payload"]["connectivity_threshold"], cancellation,
            ), {"agents": len(agents)})
            if source.get("bluesky"):
                result["collection"] = source["bluesky"]["collection"]
            return result
        finally:
            cancellation.set()

    return handle


@router.get("/{analysis_id}/pairs")
async def connectivity_pairs(
    analysis_id: str, request: Request,
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    agent_id: str | None = None, group_id: str | None = None, pair_id: str | None = None,
    connected_only: bool = False,
):
    with request.app.state.database.connect() as connection:
        record = connectivity_record(connection, analysis_id)
        filters = [agent_pairs.c.job_id == record["job_id"]]
        if agent_id:
            filters.append(or_(agent_pairs.c.source_id == agent_id, agent_pairs.c.target_id == agent_id))
        if group_id:
            group = next((group for group in record["result"]["clusters"] if group["id"] == group_id), None)
            if group is None:
                raise HTTPException(404, "Unknown connected group")
            filters.extend([agent_pairs.c.source_id.in_(group["account_ids"]),
                            agent_pairs.c.target_id.in_(group["account_ids"])])
        if pair_id:
            filters.append(agent_pairs.c.id == pair_id)
        if connected_only:
            filters.append(agent_pairs.c.weight > 0)
        total = connection.execute(select(func.count()).select_from(agent_pairs).where(*filters)).scalar_one()
        rows = connection.execute(select(agent_pairs).where(*filters).order_by(
            agent_pairs.c.score.desc(), agent_pairs.c.source_id, agent_pairs.c.target_id
        ).offset(offset).limit(limit)).mappings()
        return {"analysis_id": analysis_id, "total": total, "offset": offset, "limit": limit,
                "items": [dict(row) for row in rows]}
