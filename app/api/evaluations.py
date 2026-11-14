"""Small resumable evaluation jobs and separate corpus/provenance inspection."""

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.contracts import JobRecord
from app.evaluation.metrics import audit_corpus, evaluate_predictions
from app.evaluation.runner import load_records

router = APIRouter(prefix="/api/v1")


class EvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corpus: Literal["synthetic", "web"] = "synthetic"
    record_ids: list[str] = Field(min_length=1, max_length=10)


@router.post("/evaluations", status_code=202, response_model=JobRecord)
async def submit_evaluation(body: EvaluationInput, request: Request):
    state = request.app.state
    if not state.live:
        raise HTTPException(
            503, "Live providers are required for a new evaluation; saved metrics remain available."
        )
    known = {r["id"] for r in load_records(body.corpus)}
    if not set(body.record_ids) <= known or len(set(body.record_ids)) != len(body.record_ids):
        raise HTTPException(422, "Select unique existing record IDs")
    return state.jobs.submit("evaluation", body.corpus, body.model_dump(), state.config.versions)


@router.get("/evaluations/{job_id}")
async def evaluation_job(job_id: str, request: Request):
    record = request.app.state.jobs.get(job_id)
    if record["kind"] != "evaluation":
        raise HTTPException(404, "Unknown evaluation")
    return record


@router.get("/evaluation-corpora/{kind}")
async def corpus_summary(
    kind: Literal["synthetic", "web"],
    request: Request,
    split: Literal["all", "development", "validation", "test"] = "all",
):
    records = load_records(kind)
    selected = [r for r in records if split == "all" or r["split"] == split]
    predictions = {}
    for path in Path(".local-data/predictions").glob("*.json"):
        prediction = json.loads(path.read_text())
        if prediction["result"]["versions"] == request.app.state.config.versions:
            predictions[prediction["id"]] = prediction
    return {
        "corpus": kind,
        "audit": audit_corpus(records),
        "metrics": evaluate_predictions(selected, predictions, request.app.state.config.features),
        "records": [
            {
                "id": r["id"],
                "split": r["split"],
                "label": r["reference_annotation"]["dominant_family"],
                "preview": r["text"][:200],
                "evaluated": r["id"] in predictions,
            }
            for r in selected
        ],
    }


@router.get("/evaluation-records/{kind}/{record_id}")
async def evaluation_record(kind: Literal["synthetic", "web"], record_id: str):
    record = next((r for r in load_records(kind) if r["id"] == record_id), None)
    if not record:
        raise HTTPException(404, "Unknown corpus record")
    predictions = [json.loads(p.read_text()) for p in Path(".local-data/predictions").glob("*.json")]
    prediction = next((p for p in reversed(predictions) if p["id"] == record_id), None)
    return {"record": record, "prediction": prediction}
