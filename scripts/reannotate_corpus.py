"""Repair prior reference labels using evidence-only inputs; preserve rejected candidates."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy

from app.evaluation.corpus import ReferenceBatch, annotation_inputs, write_record


async def repair():
    source, output = Path(".local-data/corpus-unblinded-v1"), Path(".local-data/corpus")
    rejected = Path(".local-data/corpus-rejected-v2")
    rejected.mkdir(exist_ok=True)
    records = [
        json.loads(p.read_text())
        for p in sorted(source.glob("*-*.json"))
        if not (output / p.name).exists() and not (rejected / p.name).exists()
    ]
    queue = asyncio.Queue()
    for start in range(0, len(records), 24):
        queue.put_nowait(records[start : start + 24])
    client = AsyncOpenAI(timeout=160, max_retries=1)
    jev = AsyncTypeSafeClient(model="jev-latest", timeout=60, retry=RetryPolicy(max_retries=1))

    async def worker():
        while not queue.empty():
            batch = queue.get_nowait()
            try:
                response = await client.responses.parse(
                    model="gpt-6.1-sol",
                    text_format=ReferenceBatch,
                    store=False,
                    max_output_tokens=24000,
                    instructions=(
                        "Independently annotate each supplied material using only its text and reference/comparison evidence. "
                        "IDs are opaque. No generator intent or prior judgment is available. Ordinary reporting, advocacy, "
                        "emotion, accurate expert citations and rejected quotations are not manipulation. Choose none for "
                        "clearly benign material, uncertain if ambiguous. Otherwise choose the dominant established "
                        "manipulative family and secondary families. Copy exact supporting excerpts and give concise "
                        "evidence-grounded rationales. Do not search the web for these fictional scenarios."
                    ),
                    input=json.dumps(annotation_inputs(batch)),
                )
                references = {r.id: r.model_dump() for r in response.output_parsed.records}
                accepted = 0
                for index, record in enumerate(batch):
                    reference = references.get(str(index))
                    valid = (
                        reference
                        and reference["dominant_family"] == record["intent"]
                        and reference["confidence"] >= 0.8
                        and all(q.strip() and q in record["text"] for q in reference["excerpts"])
                        and (record["intent"] == "none" or reference["excerpts"])
                    )
                    quality = None
                    if valid:
                        check = await jev.system_one(
                            state={**annotation_inputs([record])[0], "reference": reference},
                            questions={
                                "quality": Choice(
                                    instructions="Does the proposed annotation follow from the text and evidence, preserving speaker/stance attribution?",
                                    criteria={
                                        "accept": "Specific, grounded and unambiguous annotation; benign cases are clearly benign.",
                                        "reject": "Unsupported, ambiguous, mistaken or inadequate comparison/factual evidence.",
                                    },
                                )
                            },
                        )
                        quality = check.choices["quality"].model_dump()
                        valid = quality["choice"] == "accept" and quality["confidence"] >= 0.7
                    if reference:
                        reference["id"] = record["id"]
                    record["reference_annotation"] = reference
                    record["quality_check"] = quality
                    record["provenance"].update(
                        protocol="corpus-v2-blinded",
                        annotator=response.model,
                        annotation_response_id=response.id,
                        annotation_usage=response.usage.model_dump() if response.usage else None,
                    )
                    write_record((output if valid else rejected) / (record["id"] + ".json"), record)
                    accepted += bool(valid)
                print(
                    json.dumps(
                        {"reannotated": len(batch), "accepted": accepted, "rejected": len(batch) - accepted}
                    ),
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 — preserve other completed batches
                print(
                    json.dumps({"error": type(exc).__name__, "status": getattr(exc, "status_code", None)}),
                    flush=True,
                )
            queue.task_done()

    try:
        await asyncio.gather(*(worker() for _ in range(4)))
    finally:
        await client.close()
        await jev.aclose()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(repair())
