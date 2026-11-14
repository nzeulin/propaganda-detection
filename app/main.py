"""Local FastAPI entry point; offline examples are an explicit input mode."""

import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from app.api.datasets import router as datasets_router
from app.content.config import Configuration
from app.content.examples import EXAMPLES, DemoProvider
from app.content.ingestion import fetch_article
from app.content.pipeline import analyze_content
from app.content.schemas import AnalysisResponse, AnalyzeRequest
from app.core.database import open_database


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
    yield
    app.state.database.dispose()
    if app.state.live:
        await app.state.live.close()


app = FastAPI(title="VeritasScope · experimental content screening", version="0.1.0", lifespan=lifespan)


app.include_router(datasets_router)


@app.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "demo_available": True,
        "live_configured": request.app.state.live is not None,
        "enabled_modes": ["text_only"],
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
        provider = state.live
        original, title, source_url = body.text, body.title, None
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
