"""Durable analysis submission, inspection, explicit retry and cancellation."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.contracts import JobRecord
from app.api.datasets import import_dataset
from app.api.swarm import SwarmInput, submit_swarm
from app.content.examples import EXAMPLES, DemoProvider
from app.content.ingestion import fetch_article
from app.content.pipeline import analyze_content
from app.content.screening import scoring_signature, with_post_screening
from app.content.verification import verify_content
from app.core.database import analyses, entities, jobs
from app.core.ingestion import DatasetInput, canonical_id
from app.swarm.bluesky import COLLECTION_VERSION
from app.swarm.engine import VERSION as SWARM_VERSION

router = APIRouter(prefix="/api/v1")


class ContentJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_id: str
    verification: Literal["none", "sol"] = "sol"


def post_job_record(record, config):
    """Read completed post jobs using the current decision policy, leaving stored history intact."""
    if (record["kind"] == "content" and record["status"] == "completed"
            and record["payload"].get("verification") == "none"):
        return {**record, "result": with_post_screening(record["result"], config)}
    return record


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
            "packaged synthetic fixture" if example_id else "Luna / Jev",
        )
        result["original_url"] = data.get("url")
        if example_id:
            result["investigation_status"] = "offline_text_fixture"
            result["warnings"].append(
                "Labeled synthetic text fixture: provider scores are packaged examples, not live verification."
            )
            return result
        if job["payload"].get("verification") == "none":
            return with_post_screening(result, state.config)
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
    payload = body.model_dump()
    if body.verification == "none":
        payload["scoring_signature"] = scoring_signature(state.config)
    with state.database.connect() as connection:
        node = connection.execute(
            select(entities).where(entities.c.id == body.content_id, entities.c.kind == "content")
        ).first()
        cached = None
        if body.verification == "none":
            fingerprint = canonical_id("content", body.content_id, payload, state.config.versions)
            cached = connection.execute(
                select(jobs)
                .where(
                    jobs.c.fingerprint == fingerprint,
                    jobs.c.status == "completed",
                )
                .order_by(jobs.c.created_at.desc())
                .limit(1)
            ).mappings().first()
    if node is None:
        raise HTTPException(404, "Unknown content")
    if cached:
        return post_job_record(dict(cached), state.config)
    if state.live is None:
        raise HTTPException(503, "Live analysis requires OPENAI_API_KEY and TYPESAFE_API_KEY.")
    return state.jobs.submit("content", body.content_id, payload, state.config.versions)


@router.get("/jobs/{job_id}", response_model=JobRecord)
async def get_job(job_id: str, request: Request):
    return post_job_record(request.app.state.jobs.get(job_id), request.app.state.config)


@router.post("/jobs/{job_id}/cancel", response_model=JobRecord)
async def cancel_job(job_id: str, request: Request):
    record = await request.app.state.jobs.cancel(job_id)
    return post_job_record(record, request.app.state.config)


@router.post("/jobs/{job_id}/retry", status_code=202, response_model=JobRecord)
async def retry_job(job_id: str, request: Request):
    state = request.app.state
    old = state.jobs.get(job_id)
    if old["status"] in ("queued", "running", "completed"):
        raise HTTPException(409, "Only failed, cancelled, or interrupted jobs can be retried.")
    if old["kind"] == "content" and old["payload"].get("verification") == "none":
        return await submit_content(ContentJobInput(content_id=old["target_id"], verification="none"), request)
    if old["kind"] == "agent_connectivity":
        return await submit_swarm(SwarmInput.model_validate(old["payload"]), request)
    configuration = {"coordination": SWARM_VERSION} if old["kind"] == "swarm" else state.config.versions
    if old["kind"] == "bluesky":
        configuration = {"bluesky": COLLECTION_VERSION}
    return state.jobs.submit(old["kind"], old["target_id"], old["payload"], configuration)


@router.get("/content/{content_id}/analysis")
async def content_analysis(content_id: str, request: Request, revision: str | None = None):
    query = select(analyses).where(analyses.c.target_id == content_id, analyses.c.kind == "content")
    if revision:
        query = query.where(analyses.c.id == revision)
    with request.app.state.database.connect() as connection:
        record = connection.execute(query.order_by(analyses.c.created_at.desc()).limit(1)).mappings().first()
    if not record:
        raise HTTPException(404, "No saved analysis")
    record = dict(record)
    if record["result"].get("propaganda_screening"):
        record["result"] = with_post_screening(record["result"], request.app.state.config)
    return record


@router.get("/analyses/{analysis_id}/trace")
async def analysis_trace(analysis_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        record = connection.execute(select(analyses).where(analyses.c.id == analysis_id)).mappings().first()
    if not record:
        raise HTTPException(404, "Unknown analysis")
    return request.app.state.jobs.get(record["job_id"])["trace"]
