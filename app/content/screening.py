"""Heuristic post screening, independent of coordination and external verification."""

import os
from math import fsum

from app.content.policy import weighted_contributions
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
    policy = config.policy["weighted_scoring"]
    score = fsum(weighted_contributions(result["features"], policy["weights"], normalize=False).values())
    if score >= policy["propaganda_threshold"]:
        label = "propaganda"
        reason = f"Meets the propaganda threshold ({policy['propaganda_threshold'] * 100:g}/100)."
    elif score >= policy["review_threshold"]:
        label = "requires_further_analysis"
        reason = f"Meets the review threshold ({policy['review_threshold'] * 100:g}/100)."
    else:
        label = "not_propaganda"
        reason = f"Below the review threshold ({policy['review_threshold'] * 100:g}/100)."
    return {
        "label": label,
        "weighted_score": score,
        "complete": True,
        "reason": f"Weighted indicator score: {score * 100:.1f}/100. {reason} Missing scores count as zero.",
        "thresholds": {"review": policy["review_threshold"], "propaganda": policy["propaganda_threshold"]},
        "policy_version": config.policy["version"],
        "experimental": True,
    }


def with_post_screening(result, config):
    """Project current post defaults without changing saved assessments or scoring cache identity."""
    features = dict(result["features"])
    features.update({key: features.get(key) or 0.0
                     for key in config.policy["weighted_scoring"]["weights"]})
    return {
        **result,
        "features": features,
        "propaganda_screening": screen_content({"features": features}, config),
    }
