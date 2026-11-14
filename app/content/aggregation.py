"""Authoritative hierarchical weighted means, coverage and exact feature contributions."""

from math import fsum


def aggregate(claims: list[dict], sections: list[dict], assessments: dict, config):
    warnings = []
    used_sections = [s for s in sections if any(c["section_id"] == s["id"] for c in claims)]
    for target, prefix in [(s, "section") for s in sections] + [(c, "claim") for c in claims]:
        record = assessments.get(f"{prefix}:{target['id']}", {}).get("relevance")
        target.update(
            relevance=record.score if record else None,
            relevance_assessment=record.model_dump() if record else None,
            weight=None,
        )
        if prefix == "claim":
            target.update(local_weight=None, role_coefficient=config.roles["coefficients"][target["role"]])
    # Missing relevance cannot be interpreted as zero or repaired by a zero-relevance fallback.
    weights_ready = (
        bool(claims)
        and all(assessments.get(f"section:{s['id']}", {}).get("relevance") is not None for s in used_sections)
        and all(assessments.get(f"claim:{c['id']}", {}).get("relevance") is not None for c in claims)
    )
    if weights_ready:
        total = fsum(assessments[f"section:{s['id']}"]["relevance"].score for s in used_sections)
        if total == 0:
            warnings.append("All section relevance is zero; uniform section weights used.")
        for section in used_sections:
            section_score = assessments[f"section:{section['id']}"]["relevance"]
            section.update(
                relevance=section_score.score,
                relevance_assessment=section_score.model_dump(),
                weight=section_score.score / total if total else 1 / len(used_sections),
            )
            local = [c for c in claims if c["section_id"] == section["id"]]
            denominator = fsum(c["relevance"] * c["role_coefficient"] for c in local)
            if denominator == 0:
                warnings.append(
                    f"All weighted relevance in {section['id']} is zero; uniform claim weights used."
                )
            for claim in local:
                claim["local_weight"] = (
                    claim["relevance"] * claim["role_coefficient"] / denominator
                    if denominator
                    else 1 / len(local)
                )
                claim["weight"] = section["weight"] * claim["local_weight"]
    features = dict.fromkeys(config.features)
    metadata, diagnostic = {}, {}
    for feature in config.features:
        reason = config.taxonomy["features"][feature]
        coverage, estimate = 0.0, None
        if feature in config.statement_features:
            eligible = []
            for claim in claims:
                record = assessments.get(f"claim:{claim['id']}", {}).get(feature)
                attributable = claim["author_attributable"] and claim["stance"] == "endorsed"
                claim["features"][feature] = record.score if record and attributable else None
                claim["assessments"][feature] = record.model_dump() if record and attributable else None
                claim["assessment_status"][feature] = (
                    "assessed" if record and attributable else "not_assessed"
                )
                if record and attributable and weights_ready:
                    eligible.append(claim)
            coverage = fsum(c["weight"] for c in eligible)
            if coverage:
                for claim in eligible:
                    claim["contributions"][feature] = claim["weight"] * claim["features"][feature] / coverage
                estimate = fsum(c["contributions"][feature] for c in eligible)
                if coverage + 1e-12 >= config.policy["minimum_coverage"]:
                    features[feature] = estimate
            reason = (
                "Assessed author-attributable statement evidence."
                if features[feature] is not None
                else "Insufficient author-attributable assessment coverage or missing relevance scores."
            )
        elif feature in ("repetition_amplification", "strategic_persuasion"):
            record = assessments.get("material", {}).get(feature)
            if record:
                features[feature], coverage, estimate = record.score, 1.0, record.score
                reason = "Document-level rubric assessment."
        metadata[feature] = {
            "status": "assessed" if features[feature] is not None else "not_assessed",
            "coverage": coverage,
            "reason": reason,
            "scope": "within_material" if feature == "repetition_amplification" else "text_only",
            "assessment": (
                assessments.get("material", {}).get(feature).model_dump()
                if assessments.get("material", {}).get(feature)
                else None
            ),
        }
        diagnostic[feature] = {"partial_estimate": estimate, "coverage": coverage}
        if config.policy["top_three_diagnostic"] and feature in config.statement_features:
            ranked = sorted(
                (c for c in claims if c["features"].get(feature) is not None and c["weight"] is not None),
                key=lambda c: c["weight"],
                reverse=True,
            )[:3]
            mass = fsum(c["weight"] for c in ranked)
            diagnostic[feature]["top_three"] = {
                "score": fsum(c["weight"] * c["features"][feature] for c in ranked) / mass if mass else None,
                "claim_ids": [c["id"] for c in ranked],
                "authoritative": False,
            }
    if claims and not weights_ready:
        warnings.append("Relevance assessment incomplete; statement-derived profile withheld.")
    return features, metadata, diagnostic, warnings
