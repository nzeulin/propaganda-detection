"""Local FastAPI entry point; offline examples are an explicit input mode."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from app.api.bluesky import collection_handler
from app.api.bluesky import router as bluesky_router
from app.api.datasets import import_dataset
from app.api.datasets import router as datasets_router
from app.api.evaluations import router as evaluations_router
from app.api.jobs import content_handler
from app.api.jobs import router as jobs_router
from app.api.swarm import router as swarm_router
from app.api.swarm import swarm_handler
from app.api.system import router as system_router
from app.content.config import Configuration
from app.content.examples import EXAMPLES, DemoProvider
from app.content.ingestion import fetch_article
from app.content.pipeline import analyze_content
from app.content.schemas import AnalysisResponse, AnalyzeRequest
from app.core.database import entities, open_database
from app.core.ingestion import DatasetInput
from app.core.jobs import JobRunner
from app.evaluation.runner import evaluation_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.database = open_database(os.getenv("DATABASE_PATH", ".local-data/investigations.db"))
    app.state.config = Configuration()
    app.state.slots = asyncio.Semaphore(2)
    app.state.live = None
    if os.getenv("OPENAI_API_KEY") and os.getenv("TYPESAFE_API_KEY"):
        from app.providers.live import LiveProvider

        app.state.live = LiveProvider(app.state.config)
    app.state.jobs = JobRunner(
        app.state.database,
        {
            "content": content_handler(app.state),
            "swarm": swarm_handler(app.state),
            "bluesky": collection_handler(app.state),
            "evaluation": evaluation_handler(app.state),
        },
    )
    app.state.slots = app.state.jobs.slots
    try:
        yield
    finally:
        await app.state.jobs.close()
        if app.state.live:
            await app.state.live.close()
        app.state.database.dispose()


app = FastAPI(title="VeritasScope · experimental content screening", version="0.1.0", lifespan=lifespan)


app.include_router(datasets_router)
app.include_router(jobs_router)
app.include_router(swarm_router)
app.include_router(bluesky_router)
app.include_router(system_router)
app.include_router(evaluations_router)


@app.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "demo_available": True,
        "live_configured": request.app.state.live is not None,
        "enabled_modes": ["text_only", "swarm"],
    }


@app.get("/examples")
async def examples():
    return [{k: example[k] for k in ("id", "title", "label", "text")} for example in EXAMPLES.values()]


@app.post("/analyze", response_model=AnalysisResponse, response_model_exclude_unset=True)
async def analyze(body: AnalyzeRequest, request: Request):
    state = request.app.state
    demo = body.example_id is not None
    if demo:
        example = EXAMPLES.get(body.example_id)
        if example is None:
            raise HTTPException(404, "Unknown demo example. Get sample IDs from /examples.")
        original, title, source_url = example["text"], body.title or example["title"], None
        provider = DemoProvider(body.example_id)
    else:
        if state.live is None:
            raise HTTPException(
                503,
                "Live analysis requires OPENAI_API_KEY and TYPESAFE_API_KEY. Choose a labeled demo or configure both keys.",
            )
        dataset = await import_dataset(
            DatasetInput(name=(body.title or "Content investigation")[:200], text=body.text, url=body.url),
            request,
        )
        with state.database.connect() as connection:
            content_id = (
                connection.execute(
                    entities.select().where(
                        entities.c.dataset_id == dataset["id"], entities.c.kind == "content"
                    )
                )
                .mappings()
                .one()["id"]
            )
        job = state.jobs.submit("content", content_id, {"content_id": content_id}, state.config.versions)
        await asyncio.shield(state.jobs.tasks[job["id"]])
        saved = state.jobs.get(job["id"])
        if saved["status"] != "completed":
            raise HTTPException(
                502, f"{(saved.get('error') or {}).get('message', saved['status'])} Saved job: {job['id']}"
            )
        result = {key: value for key, value in saved["result"].items() if key != "analysis_id"}
        if not body.include_details:
            for key in ("statements", "sections", "contextual_findings", "diagnostics", "annotations"):
                result.pop(key)
        return result
    try:
        async with asyncio.timeout(240):
            async with state.slots:
                if not demo and body.url:
                    original, fetched_title, source_url = await fetch_article(body.url)
                    title = title or fetched_title
                result = await analyze_content(original, title, provider, state.config, source_url, demo)
                result["original_url"] = body.url
    except TimeoutError as exc:
        raise HTTPException(504, "Analysis timed out. Try a shorter article.") from exc
    if not body.include_details:
        for key in ("statements", "sections", "contextual_findings", "diagnostics", "annotations"):
            result.pop(key)
    return result


# Hash-based navigation allows a single origin without intercepting API routes.
frontend_dist = Path(os.getenv("FRONTEND_DIST", "frontend/dist"))
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
