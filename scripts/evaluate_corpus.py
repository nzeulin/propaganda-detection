"""Evaluate frozen records independently; successful predictions are resumable artifacts."""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from app.content.config import Configuration
from app.evaluation.metrics import evaluate_predictions
from app.evaluation.runner import evaluate_record, load_records
from app.providers.live import LiveProvider


async def run(kind, split, limit, concurrency, pilot):
    config = Configuration()
    provider = LiveProvider(config)
    records = [r for r in load_records(kind) if r["split"] == split]
    if pilot:
        families = {}
        for record in records:
            families.setdefault(record["reference_annotation"]["dominant_family"], record)
        records = list(families.values())
    else:
        records = records[:limit]
    queue = asyncio.Queue()
    for record in records:
        queue.put_nowait(record)
    predictions = {}

    async def worker():
        while not queue.empty():
            record = queue.get_nowait()
            try:
                prediction = await evaluate_record(record, provider, config, Path(".local-data/predictions"))
                predictions[record["id"]] = prediction
                print(
                    json.dumps(
                        {
                            "id": record["id"],
                            "seconds": prediction["seconds"],
                            "label": prediction["result"]["classification"]["label"],
                        }
                    ),
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 — retain successful records across a batch failure
                print(
                    json.dumps(
                        {"failed": record["id"], "error": type(exc).__name__, "message": str(exc)[:200]}
                    ),
                    flush=True,
                )
            queue.task_done()

    try:
        await asyncio.gather(*(worker() for _ in range(concurrency)))
    finally:
        await provider.close()
    metrics = evaluate_predictions(records, predictions, config.features)
    Path(f".local-data/{kind}-{split}-metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", choices=["synthetic", "web"], default="synthetic")
    parser.add_argument("--split", choices=["development", "validation", "test"], default="development")
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--concurrency", type=int, choices=[1, 2], default=2)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    asyncio.run(run(args.corpus, args.split, args.limit, args.concurrency, args.pilot))
