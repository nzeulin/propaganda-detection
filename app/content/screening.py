"""Heuristic post screening, independent of coordination and external verification."""

import os

from app.content.policy import assessed_features, material_score
from app.core.ingestion import canonical_id


def scoring_signature(config):
    """Invalidate saved scores when configured models or any scoring configuration changes."""
    return canonical_id(
        "swarm-content-scoring-v1",
        {name: getattr(config, name) for name in ("taxonomy", "rubrics", "roles", "policy", "prompts")},
        {
            "extractor": os.getenv("OPENAI_MODEL", "gpt-6-luna"),
            "scorer": os.getenv("TYPESAFE_MODEL", "jev-latest"),
        },
    )


def screen_content(result, config):
    """Use the same evidence requirements and score as material text analysis."""
    policy = config.policy["weighted_scoring"]
    blocked_reason = None
    if result.get("review_required"):
        blocked_reason = "Combined material score withheld: narrative review required."
    elif "statements" in result and not result["statements"]:
        blocked_reason = "No valid statements were extracted."
    assessment = material_score(assessed_features(result), config, blocked_reason=blocked_reason)
    label = {
        "not_suspicious": "not_propaganda",
        "suspicious": "requires_further_analysis",
        "requires_review": "requires_further_analysis",
        "not_assessed": "requires_further_analysis",
        "propaganda": "propaganda",
    }[assessment["label"]]
    return {
        "label": label,
        "weighted_score": assessment["value"],
        "complete": assessment["status"] == "assessed",
        "reason": assessment["reason"],
        "thresholds": {"review": policy["review_threshold"], "propaganda": policy["propaganda_threshold"]},
        "policy_version": config.policy["version"],
        "experimental": True,
    }


def with_post_screening(result, config):
    """Preserve unknown assessments when projecting current post decisions."""
    return {
        **result,
        "features": assessed_features(result),
        "propaganda_screening": screen_content(result, config),
    }
