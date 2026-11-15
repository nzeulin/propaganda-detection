"""Symmetric verification escalation and evidence-gated feature aggregation."""

import asyncio
from math import fsum


def escalation_reasons(result, report, config):
    reasons = []
    if not report["checks"]:
        reasons.append("No claims were checked")
    for check in report["checks"]:
        relation = check.get("relation", {})
        if check["kind"] in ("factual", "unclear") and relation.get("choice") not in (
            "supported",
            "contradicted",
        ):
            reasons.append("Missing or conflicting factual evidence")
        if check["date_uncertain"] or check["attribution_uncertain"]:
            reasons.append("Date or attribution uncertainty")
        if check["kind"] == "factual" and relation and relation.get("confidence", 0) < 0.70:
            reasons.append("Evidence relation confidence below 0.70")
        if (
            relation.get("choice") == "contradicted"
            and result["classification"]["label"] == "no_strong_text_indicators"
        ):
            reasons.append("Evidence disagrees with preliminary text assessment")
        if (
            relation.get("choice") == "supported"
            and result["classification"]["label"] in ("suspicious", "propaganda", "indicators_detected")
        ):
            reasons.append("Text indicators coexist with supported factual claims")
    if any(
        result["coverage"][k] < config.policy["minimum_coverage"] for k in config.policy["required_features"]
    ):
        reasons.append("Insufficient text coverage")
    score = result["classification"].get("weighted_score")
    if score is not None and any(
        abs(score - boundary) <= 0.10
        for boundary in (
            config.policy["weighted_scoring"]["review_threshold"],
            config.policy["weighted_scoring"]["propaganda_threshold"],
        )
    ):
        reasons.append("Score near an experimental policy boundary")
    return list(dict.fromkeys(reasons))


async def verify_content(result, provider, config, stage, evidence_packet=None):
    claims = {c["id"]: c for c in result["statements"]}

    async def assess(report):
        slots = asyncio.Semaphore(4)

        async def check(record):
            claim = claims[record["claim_id"]]
            if record["kind"] != "factual" or not record["evidence"]:
                record["relation"] = {"choice": "insufficient", "confidence": 0, "probabilities": {}}
                return
            async with slots:
                record["relation"] = await provider.scorer.evidence_relation(
                    claim["text"], record["evidence"]
                )
                questions = []
                if (
                    record["relation"]["choice"] in ("supported", "contradicted")
                    and record["relation"]["confidence"] >= 0.70
                ):
                    questions.append("factual_manipulation")
                if record["comparison_evidence"]:
                    questions.append("selective_presentation")
                if questions and claim["author_attributable"] and claim["stance"] == "endorsed":
                    assessments = await provider.score(
                        {
                            "article": result["normalized_text"],
                            "target": claim,
                            "evidence": record["evidence"],
                            "comparison_corpus": record["comparison_evidence"],
                            "relation": record["relation"],
                        },
                        questions,
                    )
                    record["assessments"] = {k: v.model_dump() for k, v in assessments.items()}

        await asyncio.gather(*(check(record) for record in report["checks"]))
        return report

    report = await stage(
        "verification_initial",
        lambda: provider.verifier.research(
            result, **({"packaged_sources": evidence_packet} if evidence_packet is not None else {})
        ),
        {"claim_ids": list(claims)},
        provider.verifier.model,
    )
    report = await stage("evidence_initial", lambda: assess(report), provider=provider.scorer.model)
    reasons = escalation_reasons(result, report, config)
    if reasons:
        previous = report
        report = await stage(
            "verification_deeper",
            lambda: provider.verifier.research(
                result,
                previous,
                **({"packaged_sources": evidence_packet} if evidence_packet is not None else {}),
            ),
            {"reasons": reasons},
            provider.verifier.model,
        )
        report = await stage("evidence_deeper", lambda: assess(report), provider=provider.scorer.model)
    report.update(escalated=bool(reasons), escalation_reasons=reasons, version="verification-v1")
    unresolved = [
        c["claim_id"]
        for c in report["checks"]
        if c["kind"] in ("factual", "unclear")
        and (
            c.get("relation", {}).get("choice") not in ("supported", "contradicted")
            or c.get("relation", {}).get("confidence", 0) < 0.70
            or c["date_uncertain"]
            or c["attribution_uncertain"]
        )
    ]
    report.update(
        status="needs_review" if unresolved or not claims else "complete", unchecked_claim_ids=unresolved
    )
    for feature in ("factual_manipulation", "selective_presentation"):
        eligible = []
        for check in report["checks"]:
            assessment = check.get("assessments", {}).get(feature)
            claim = claims[check["claim_id"]]
            if assessment and claim.get("weight") is not None:
                score = assessment["raw_score"] / 4
                claim["features"][feature] = score
                claim["assessments"][feature] = assessment
                eligible.append((claim, score))
        coverage = fsum(c["weight"] for c, _ in eligible)
        for claim, score in eligible:
            claim["contributions"][feature] = claim["weight"] * score / coverage if coverage else 0
        for claim, local_score in eligible:
            if local_score < config.policy["highlight_yellow"]:
                continue
            for occurrence in claim["occurrences"]:
                for span in occurrence["source_spans"]:
                    result["annotations"].append(
                        {
                            "id": f"evidence-{len(result['annotations']) + 1}",
                            **span,
                            "feature": feature,
                            "score": local_score,
                            "claim_id": claim["id"],
                            "attribution": claim["stance"],
                            "speaker": occurrence["speaker"],
                            "speaker_name": occurrence["speaker_name"],
                            "contribution": claim["contributions"][feature],
                            "contribution_scope": "canonical_claim",
                            "rubric": config.rubrics[feature],
                            "assessment": claim["assessments"][feature],
                        }
                    )
        estimate = fsum(c["contributions"][feature] for c, _ in eligible) if coverage else None
        score = (
            estimate
            if coverage >= config.policy["minimum_coverage"] and not result["review_required"]
            else None
        )
        result["features"][feature] = score
        result["coverage"][feature] = coverage
        result["feature_details"][feature].update(
            status="assessed" if score is not None else "not_assessed",
            coverage=coverage,
            scope="external_evidence",
            reason="Evidence-grounded assessment."
            if score is not None
            else "Insufficient applicable, attributable evidence coverage; unverified is not false.",
        )
        result["diagnostics"][feature].update(partial_estimate=estimate, coverage=coverage)
    result["availability"] = {k: v is not None for k, v in result["features"].items()}
    result["availability_mask"] = list(result["availability"].values())
    result["verification"] = report
    result["investigation_status"] = "needs_review" if result["review_required"] else report["status"]
    result["provenance"]["evidence_scope"] = (
        "packaged_synthetic_evidence" if evidence_packet is not None else "retrieved_exact_excerpts"
    )
    result["warnings"] = [
        w for w in result["warnings"] if w != "Factual claims and omissions were not externally verified."
    ]
    result["warnings"].append(
        "Text indicators are separate from factual verification; neither establishes intent."
    )
    return result
