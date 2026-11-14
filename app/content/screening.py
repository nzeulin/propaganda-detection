"""Heuristic post screening, independent of coordination and external verification."""

import os

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
    """Require sufficient attributable evidence before applying the two score thresholds."""
    policy = config.policy["propaganda_screening"]
    values = [result["features"].get(key) for key in policy["required_features"]]
    complete = (
        not result["review_required"]
        and not any(claim["stance"] == "unclear" for claim in result["statements"])
        and all(value is not None for value in values)
        and all(
            result["coverage"].get(key, 0) + 1e-12 >= config.policy["minimum_coverage"]
            for key in policy["required_features"]
        )
    )
    if not complete:
        label = "requires_further_analysis"
        reason = "Missing scores, insufficient coverage, or unresolved narrative/attribution."
    elif sum(value >= policy["propaganda_threshold"] for value in values) >= policy["minimum_strong_features"]:
        label = "propaganda"
        reason = "At least two text features meet the strong threshold."
    elif any(value >= policy["review_threshold"] for value in values):
        label = "requires_further_analysis"
        reason = "Elevated text features need further validation."
    else:
        label = "not_propaganda"
        reason = "All five assessed text features are below the review threshold."
    return {
        "label": label,
        "complete": complete,
        "reason": reason,
        "thresholds": {"review": policy["review_threshold"], "propaganda": policy["propaganda_threshold"]},
        "policy_version": policy["version"],
        "experimental": True,
    }
