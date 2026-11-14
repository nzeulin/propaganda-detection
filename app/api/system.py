"""Public module definitions and execution inventory; no credentials or hidden reasoning."""

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.core.database import jobs

router = APIRouter(prefix="/api/v1")


@router.get("/system")
async def system_description(request: Request):
    definitions = [
        (
            "ingestion",
            "Source ingestion",
            "Normalize Unicode text or safely fetch a public article. Preserve the source.",
            "local",
            [],
        ),
        (
            "extraction",
            "Claim extraction",
            "Identify narratives, speakers, stance and exact quotations.",
            "GPT-6 Luna",
            ["ingestion"],
        ),
        (
            "anchoring",
            "Exact anchoring",
            "Match quoted text locally. Reject ambiguous or invented spans.",
            "local",
            ["extraction"],
        ),
        (
            "scoring",
            "Rubric scoring",
            "Score attributable claims against explicit five-level rubrics.",
            "Jev",
            ["anchoring"],
        ),
        (
            "aggregation",
            "Weighted profile",
            "Combine section relevance, claim roles, coverage and exact contributions.",
            "local",
            ["scoring"],
        ),
        (
            "content",
            "Text assessment",
            "Preserve the complete text-indicator profile before verification.",
            "local",
            ["aggregation"],
        ),
        (
            "verification_initial",
            "Initial fact-check",
            "Research every selected live material, including apparently benign texts.",
            "GPT-6.1 Sol",
            ["content"],
        ),
        (
            "evidence_initial",
            "Evidence relations",
            "Compare claims to exact fetched excerpts; missing evidence is not falsehood.",
            "Jev",
            ["verification_initial"],
        ),
        (
            "verification_deeper",
            "Deeper fact-check",
            "One additional pass for gaps, conflicts, uncertainty or borderline scores.",
            "GPT-6.1 Sol",
            ["evidence_initial"],
        ),
        (
            "evidence_deeper",
            "Final evidence assessment",
            "Keep verified facts, unresolved claims and text indicators distinct.",
            "Jev",
            ["verification_deeper"],
        ),
        (
            "coordination",
            "Coordination analysis",
            "Compare recurrent text/URL timing to shuffled baselines, independently of content labels.",
            "local CPU",
            ["ingestion"],
        ),
        (
            "agent_connectivity",
            "Agent connectivity",
            "Combine explicit mentions and authored-content embeddings into weighted connections and connected groups.",
            "OpenAI embeddings",
            ["ingestion"],
        ),
        (
            "review",
            "Human review",
            "Record append-only decisions. Model outputs do not establish intent.",
            "reviewer",
            ["evidence_initial", "evidence_deeper", "coordination"],
        ),
    ]
    return {
        "modules": [
            {
                "id": key,
                "label": label,
                "description": description,
                "provider": provider,
                "depends_on": dependencies,
            }
            for key, label, description, provider, dependencies in definitions
        ],
        "versions": request.app.state.config.versions,
        "limits": {
            "material_jobs": 2,
            "provider_requests": 4,
            "characters": 40000,
            "search_tool_calls": 20,
            "fetched_documents": 40,
            "seconds_per_job": 600,
            "visible_graph_nodes": 300,
        },
        "live_configured": request.app.state.live is not None,
    }


@router.get("/jobs")
async def list_jobs(request: Request, target_id: str | None = None, limit: int = Query(50, ge=1, le=100)):
    query = select(jobs.c.id, jobs.c.kind, jobs.c.target_id, jobs.c.status, jobs.c.created_at)
    if target_id:
        query = query.where(jobs.c.target_id == target_id)
    with request.app.state.database.connect() as connection:
        return [
            dict(r)
            for r in connection.execute(query.order_by(jobs.c.created_at.desc()).limit(limit)).mappings()
        ]
