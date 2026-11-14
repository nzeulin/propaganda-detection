"""Self-contained content orchestration with injectable extraction/scoring providers."""

import asyncio
import hashlib

from fastapi import HTTPException

from app.content.aggregation import aggregate
from app.content.ingestion import normalize
from app.content.policy import classify
from app.content.validation import validate_and_group


async def analyze_content(
    original: str, title: str | None, provider, config, source_url=None, demo=False, stage=None
):
    async def execute(name, operation, inputs=None, provider="local"):
        if stage:
            return await stage(name, operation, inputs, provider)
        return await operation()

    text, paragraphs = normalize(original)
    warnings, claims = [], []
    extraction = None
    for attempt in range(2):
        try:
            extraction = await execute(
                "extraction",
                lambda attempt=attempt: provider.extract(text, paragraphs, title, warnings if attempt else None),
                {"paragraphs": paragraphs},
                provider.models["extractor"],
            )
            claims, issues = validate_and_group(extraction, text, paragraphs)
            if not issues:
                break
            warnings.extend(issues if attempt else ["Invalid source extraction; retried once."])
        except ValueError as exc:
            if attempt:
                raise HTTPException(502, "Extraction failed after one retry; try a shorter article.") from exc
            warnings.append("Invalid structured extraction; retried once.")
    if extraction is None:
        raise HTTPException(502, "Extraction returned no usable result.")
    sections = [s.model_dump() for s in extraction.sections]
    narratives = [n.model_dump() for n in extraction.narratives]
    context = {
        "article": text,
        "title": title,
        "narratives": narratives,
        "canonical_claims": claims,
        "paragraphs": paragraphs,
    }
    jobs = []
    for section in sections:
        if any(c["section_id"] == section["id"] for c in claims):
            jobs.append((f"section:{section['id']}", {**context, "target": section}, ["relevance"]))
    for claim in claims:
        questions = ["relevance"]
        if claim["author_attributable"] and claim["stance"] == "endorsed":
            questions += config.statement_features
        jobs.append((f"claim:{claim['id']}", {**context, "target": claim}, questions))
    if claims:
        jobs.append(
            (
                "material",
                {**context, "patterns": [p.model_dump() for p in extraction.patterns]},
                ["repetition_amplification", "strategic_persuasion"],
            )
        )
    # Limit workers as well as provider sockets; long articles cannot create unbounded fan-out.
    assessments = {}
    queue = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)

    async def worker():
        while not queue.empty():
            key, state, questions = queue.get_nowait()
            try:
                assessments[key] = await provider.score(state, questions)
            except (HTTPException, ValueError, TimeoutError) as exc:
                assessments[key] = {}
                warnings.append(f"Scoring unavailable for {key}: {getattr(exc, 'detail', str(exc))}")

    async def score_all():
        await asyncio.gather(*(worker() for _ in range(min(4, len(jobs)))))
        return {key: {k: v.model_dump() for k, v in values.items()} for key, values in assessments.items()}

    await execute("scoring", score_all, {"validated_claims": claims}, provider.models["scorer"])
    features, metadata, diagnostics, math_warnings = aggregate(claims, sections, assessments, config)
    warnings.extend(math_warnings)
    review = len(narratives) != 1
    if review:
        warnings.append(
            "Independent or missing narratives require review; combined material profile withheld."
        )
        for key in config.features:
            # Preserve evidence/coverage reasons for dimensions that were already unavailable.
            if features[key] is not None:
                features[key] = None
                metadata[key].update(
                    status="not_assessed", reason="Narrative review required; combined profile withheld."
                )
    if not claims:
        warnings.append("extraction_failed: no valid statements were extracted.")
        features = dict.fromkeys(config.features)
        for value in metadata.values():
            value.update(status="not_assessed", reason="No valid extracted statements.")
    findings = []
    for pattern in extraction.patterns:
        record = assessments.get("material", {}).get(pattern.feature)
        if record is None:
            continue
        linked = [
            c
            for c in claims
            if c["author_attributable"]
            and c["stance"] == "endorsed"
            and any(o["id"] in pattern.statement_ids for o in c["occurrences"])
        ]
        # A contextual score belongs to the entire finding, never to each linked claim.
        findings.append(
            {
                "id": f"finding{len(findings) + 1}",
                "feature": pattern.feature,
                "description": pattern.description,
                "score": record.score,
                "assessment": record.model_dump(),
                "claim_ids": [c["id"] for c in linked],
                "source_spans": [
                    span
                    for c in linked
                    for o in c["occurrences"]
                    if o["id"] in pattern.statement_ids
                    for span in o["source_spans"]
                ],
                "contribution": None,
                "contribution_scope": "material_level",
                "evidence_urls": [],
            }
        )
    annotations = []
    for claim in claims:
        if not claim["author_attributable"] or claim["stance"] != "endorsed":
            continue
        for feature, score in claim["features"].items():
            if score is None or score < config.policy["highlight_yellow"]:
                continue
            for occurrence in claim["occurrences"]:
                for span in occurrence["source_spans"]:
                    annotations.append(
                        {
                            "id": f"a{len(annotations) + 1}",
                            **span,
                            "feature": feature,
                            "score": score,
                            "claim_id": claim["id"],
                            "attribution": claim["stance"],
                            "speaker": occurrence["speaker"],
                            "speaker_name": occurrence["speaker_name"],
                            "contribution": claim["contributions"].get(feature),
                            "contribution_scope": "canonical_claim",
                            "rubric": config.rubrics[feature],
                            "assessment": claim["assessments"][feature],
                        }
                    )
    for finding in findings:
        if finding["score"] < config.policy["highlight_yellow"]:
            continue
        for span in finding["source_spans"]:
            annotations.append(
                {
                    "id": f"a{len(annotations) + 1}",
                    **span,
                    "feature": finding["feature"],
                    "score": finding["score"],
                    "claim_id": None,
                    "attribution": "endorsed",
                    "speaker": "author/endorsed source",
                    "speaker_name": None,
                    "contribution": None,
                    "contribution_scope": "material_level",
                    "rubric": config.rubrics[finding["feature"]],
                    "assessment": finding["assessment"],
                }
            )
    availability = {key: value is not None for key, value in features.items()}
    warnings += [
        "Factual claims and omissions were not externally verified.",
        "Authority fabrication is not assessed; authority scores concern misleading appeals only.",
        "Confidence describes rubric distribution concentration, not validated accuracy.",
    ]
    return {
        "material_id": hashlib.sha256(text.encode()).hexdigest()[:20],
        "title": title,
        "original_text": original,
        "normalized_text": text,
        "paragraphs": paragraphs,
        "source_url": source_url,
        "mode": "text_only",
        "demo": demo,
        "primary_narrative": narratives[0]["summary"] if narratives else None,
        "narratives": narratives,
        "review_required": review,
        "features": features,
        "availability": availability,
        "availability_mask": list(availability.values()),
        "coverage": {k: v["coverage"] for k, v in metadata.items()},
        "feature_details": metadata,
        "classification": classify(features, config, review or not claims),
        "sections": sections,
        "statements": claims,
        "contextual_findings": findings,
        "annotations": annotations,
        "diagnostics": diagnostics,
        "warnings": list(dict.fromkeys(warnings)),
        "model_versions": provider.models,
        "versions": config.versions,
        "provenance": {
            "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "offset_unit": "unicode_code_points",
            "aggregation": "hierarchical_weighted_mean",
            "evidence_scope": "text_only",
            "authority_fabrication": "not_assessed",
        },
        "highlight_thresholds": {
            "yellow": config.policy["highlight_yellow"],
            "red": config.policy["highlight_red"],
        },
    }
