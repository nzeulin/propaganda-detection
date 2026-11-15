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
    """Classify completed post scores, defaulting missing text indicators to zero."""
    policy = config.policy["propaganda_screening"]
    values = [result["features"].get(key) or 0.0 for key in policy["required_features"]]
    if sum(value >= policy["propaganda_threshold"] for value in values) >= policy["minimum_strong_features"]:
        label = "propaganda"
        reason = "At least two text features meet the strong threshold."
    elif any(value >= policy["review_threshold"] for value in values):
        label = "requires_further_analysis"
        reason = "Elevated text features need further validation."
    else:
        label = "not_propaganda"
        reason = "All five text features are below the review threshold; missing scores count as zero."
    return {
        "label": label,
        "complete": True,
        "reason": reason,
        "thresholds": {"review": policy["review_threshold"], "propaganda": policy["propaganda_threshold"]},
        "policy_version": policy["version"] + "-zero-defaults",
        "experimental": True,
    }


def with_post_screening(result, config):
    """Project current post defaults without changing saved assessments or scoring cache identity."""
    features = dict(result["features"])
    features.update({key: features.get(key) or 0.0
                     for key in config.policy["propaganda_screening"]["required_features"]})
    return {
        **result,
        "features": features,
        "propaganda_screening": screen_content({"features": features}, config),
    }
