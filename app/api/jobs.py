"""Durable analysis submission, inspection, explicit retry and cancellation."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.contracts import JobRecord
from app.api.datasets import import_dataset
from app.content.examples import EXAMPLES, DemoProvider
from app.content.ingestion import fetch_article
from app.content.pipeline import analyze_content
from app.content.verification import verify_content
from app.core.database import analyses, entities
from app.core.ingestion import DatasetInput

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
        example_id = job["payload"].get("example_id")
        provider = DemoProvider(example_id) if example_id else state.live
        text, title, url = data["text"], None, data.get("url")
        if not text:
            text, title, url = await stage("ingestion", lambda: fetch_article(url), {"url": url})
        result = await stage(
            "content",
            lambda: analyze_content(
                text, title, provider, state.config, url, demo=bool(example_id), stage=stage
            ),
            {"content_id": node["id"]},
            "Luna / Jev",
        )
        result["original_url"] = data.get("url")
        if example_id:
            result["investigation_status"] = "offline_text_fixture"
            result["warnings"].append(
                "Labeled synthetic text fixture: provider scores are packaged examples, not live verification."
            )
            return result
        return await verify_content(result, state.live, state.config, stage)

    return handle


@router.post("/demos/{example_id}", status_code=202, response_model=JobRecord)
async def submit_demo(example_id: str, request: Request):
    example = EXAMPLES.get(example_id)
    if example is None:
        raise HTTPException(404, "Unknown labeled demonstration")
    dataset = await import_dataset(
        DatasetInput(name="Synthetic demo: " + example["title"], text=example["text"]), request
    )
    with request.app.state.database.connect() as connection:
        content_id = connection.execute(
            select(entities.c.id).where(entities.c.dataset_id == dataset["id"], entities.c.kind == "content")
        ).scalar_one()
    return request.app.state.jobs.submit(
        "content", content_id, {"example_id": example_id}, request.app.state.config.versions
    )


@router.post("/content/analyze", status_code=202, response_model=JobRecord)
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


@router.get("/jobs/{job_id}", response_model=JobRecord)
async def get_job(job_id: str, request: Request):
    return request.app.state.jobs.get(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobRecord)
async def cancel_job(job_id: str, request: Request):
    return await request.app.state.jobs.cancel(job_id)


@router.post("/jobs/{job_id}/retry", status_code=202, response_model=JobRecord)
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
