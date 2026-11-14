"""Evaluate the unchanged application against evidence packets; resume by content/config hash."""

import asyncio
import hashlib
import json
import time
from pathlib import Path

from app.content.pipeline import analyze_content
from app.content.verification import verify_content
from app.core.database import utc_now
from app.core.ingestion import canonical_id
from app.evaluation.metrics import evaluate_predictions
from app.providers.usage import usage_context


def load_records(kind="synthetic"):
    directory = Path(".local-data/corpus" if kind == "synthetic" else ".local-data/web-corpus")
    records = [
        json.loads(p.read_text()) for p in sorted(directory.glob("*.json")) if p.name != "manifest.json"
    ]
    if not records:
        packaged = Path("data/synthetic_corpus.jsonl" if kind == "synthetic" else "data/web_corpus.jsonl")
        if kind == "synthetic" and not packaged.exists():
            packaged = Path("data/synthetic_pilot.jsonl")
        if packaged.exists():
            records = [json.loads(line) for line in packaged.read_text().splitlines() if line.strip()]
    return records


def load_predictions(config=None):
    packaged = Path("data/demo_predictions.jsonl")
    candidates = (
        [json.loads(line) for line in packaged.read_text().splitlines() if line.strip()]
        if packaged.exists()
        else []
    )
    candidates.extend(json.loads(path.read_text()) for path in Path(".local-data/predictions").glob("*.json"))
    predictions = {}
    for prediction in sorted(candidates, key=lambda record: record["created_at"]):
        if config is None or prediction["result"]["versions"] == config.versions:
            predictions[prediction["id"]] = prediction
    return predictions


async def evaluate_record(record, provider, config, output):
    fingerprint = canonical_id(
        record["text_sha256"],
        record.get("reference_facts"),
        record.get("comparison_corpus"),
        config.versions,
        provider.models,
    )
    path = output / f"{fingerprint}.json"
    if path.exists():
        return {**json.loads(path.read_text()), "id": record["id"]}
    trace = []
    usage_token = usage_context.set([])

    async def stage(name, operation, inputs=None, provider="local"):
        started = time.monotonic()
        value = await operation()
        trace.append({"module": name, "provider": provider, "seconds": time.monotonic() - started})
        return value

    started = time.monotonic()
    try:
        async with asyncio.timeout(600):
            result = await analyze_content(record["text"], None, provider, config)
            packet = None
            if record["provenance"]["kind"] == "synthetic":
                packet = []
                for name in ("reference_facts", "comparison_corpus"):
                    text = record.get(name, "")
                    if not text:
                        continue
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    packet.append(
                        {
                            "id": digest,
                            "text": text,
                            "content_sha256": digest,
                            "url": f"fixture:{record['scenario_id']}/{name}",
                            "requested_url": f"fixture:{record['scenario_id']}/{name}",
                            "status": "fetched",
                            "retrieved_at": utc_now(),
                            "title": "Packaged fictional scenario: " + name,
                            "source_kind": "synthetic_fixture",
                        }
                    )
            result = await verify_content(result, provider, config, stage, evidence_packet=packet)
    finally:
        usage = usage_context.get()
        usage_context.reset(usage_token)
        if usage_context.get() is not None:
            usage_context.get().extend(usage)
    prediction = {
        "provider_usage": usage,
        "id": record["id"],
        "fingerprint": fingerprint,
        "result": result,
        "seconds": round(time.monotonic() - started, 3),
        "trace": trace,
        "created_at": utc_now(),
    }
    output.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prediction, ensure_ascii=False))
    return prediction


def evaluation_handler(state):
    async def handle(job, stage):
        records = load_records(job["payload"]["corpus"])
        selected = [r for r in records if r["id"] in job["payload"]["record_ids"]]
        output = Path(".local-data/predictions")
        predictions = {}
        for record in selected:
            prediction = await stage(
                "evaluation_record",
                lambda record=record: evaluate_record(record, state.live, state.config, output),
                {
                    "record_id": record["id"],
                    "completed_units": len(predictions),
                    "total_units": len(selected),
                },
                "Luna / Sol / Jev",
            )
            predictions[record["id"]] = prediction
        return {
            "corpus": job["payload"]["corpus"],
            "record_ids": list(predictions),
            "metrics": evaluate_predictions(selected, predictions, state.config.features),
        }

    return handle
