"""Durable analysis submission, inspection, explicit retry and cancellation."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.content.ingestion import fetch_article
from app.content.pipeline import analyze_content
from app.core.database import analyses, entities

router = APIRouter(prefix="/api/v1")


class ContentJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_id: str


def content_handler(state):
    async def handle(job, stage):
        with state.database.connect() as connection:
            node = (
                connection.execute(select(entities).where(entities.c.id == job["target_id"])).mappings().one()
            )
        data = node["data"]
        text, title, url = data["text"], None, data.get("url")
        if not text:
            text, title, url = await stage("ingestion", lambda: fetch_article(url), {"url": url})
        result = await stage(
            "content",
            lambda: analyze_content(text, title, state.live, state.config, url),
            {"content_id": node["id"]},
            "Luna / Jev",
        )
        result["original_url"] = data.get("url")
        return result

    return handle


@router.post("/content/analyze", status_code=202)
async def submit_content(body: ContentJobInput, request: Request):
    state = request.app.state
    if state.live is None:
        raise HTTPException(503, "Live analysis requires OPENAI_API_KEY and TYPESAFE_API_KEY.")
    with state.database.connect() as connection:
        node = connection.execute(
            select(entities).where(entities.c.id == body.content_id, entities.c.kind == "content")
        ).first()
    if node is None:
        raise HTTPException(404, "Unknown content")
    return state.jobs.submit("content", body.content_id, body.model_dump(), state.config.versions)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    return request.app.state.jobs.get(job_id)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    return await request.app.state.jobs.cancel(job_id)


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(job_id: str, request: Request):
    state = request.app.state
    old = state.jobs.get(job_id)
    if old["status"] in ("queued", "running", "completed"):
        raise HTTPException(409, "Only failed, cancelled, or interrupted jobs can be retried.")
    return state.jobs.submit(old["kind"], old["target_id"], old["payload"], state.config.versions)


@router.get("/content/{content_id}/analysis")
async def content_analysis(content_id: str, request: Request, revision: str | None = None):
    query = select(analyses).where(analyses.c.target_id == content_id, analyses.c.kind == "content")
    if revision:
        query = query.where(analyses.c.id == revision)
    with request.app.state.database.connect() as connection:
        record = connection.execute(query.order_by(analyses.c.created_at.desc()).limit(1)).mappings().first()
    if not record:
        raise HTTPException(404, "No saved analysis")
    return dict(record)


@router.get("/analyses/{analysis_id}/trace")
async def analysis_trace(analysis_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        record = connection.execute(select(analyses).where(analyses.c.id == analysis_id)).mappings().first()
    if not record:
        raise HTTPException(404, "Unknown analysis")
    return request.app.state.jobs.get(record["job_id"])["trace"]
