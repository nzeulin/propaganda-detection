"""Experimental screening policy, never a calibrated truth or propaganda verdict."""

from math import fsum


def weighted_contributions(features, weights, *, normalize=True):
    """Return weighted contributions, optionally normalizing over the available evidence."""
    available = {key: features[key] for key in weights if features.get(key) is not None}
    total = fsum(weights[key] for key in available) if normalize else 1.0
    return {key: weights[key] * value / total for key, value in available.items()}


def classify(features: dict, config, blocked: bool = False):
    required = config.policy["required_features"]
    policy = config.policy["weighted_scoring"]
    contributions = weighted_contributions(features, policy["weights"])
    score = None
    if blocked or any(features[k] is None for k in required):
        label = "inconclusive"
    else:
        score = fsum(contributions.values())
        label = (
            "propaganda" if score >= policy["propaganda_threshold"]
            else "suspicious" if score >= policy["review_threshold"]
            else "no_strong_text_indicators"
        )
    elevated = label in ("suspicious", "propaganda")
    return {
        "mode": "text_only",
        "label": label,
        "weighted_score": score,
        "risk_score": None,
        "policy_version": config.policy["version"],
        "experimental": True,
        "trigger_features": (
            [key for key in sorted(contributions, key=lambda key: -contributions[key]) if contributions[key] > 0]
            if elevated else []
        ),
        "strong_features": (
            [key for key in contributions if features[key] >= config.policy["strong_threshold"]]
            if elevated else []
        ),
    }
