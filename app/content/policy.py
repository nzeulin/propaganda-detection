"""Experimental screening policy, never a calibrated truth or propaganda verdict."""

from math import fsum


def weighted_contributions(features, weights, *, normalize=True):
    """Return weighted contributions, optionally normalizing over the available evidence."""
    available = {key: features[key] for key in weights if features.get(key) is not None}
    total = fsum(weights[key] for key in available) if normalize else 1.0
    return {key: weights[key] * value / total for key, value in available.items()}


def assessed_features(result):
    """Recover unknowns in historical post responses that defaulted missing evidence to zero."""
    details = result.get("feature_details", {})
    return {
        key: None if details.get(key, {}).get("status") == "not_assessed" else value
        for key, value in result["features"].items()
    }


def material_score(features, config, *, blocked_reason=None):
    """Share one evidence gate, normalized score and decision across text and post views."""
    policy = config.policy["weighted_scoring"]
    contributions = weighted_contributions(features, policy["weights"])
    missing = [key for key in config.policy["required_features"] if features.get(key) is None]
    value = None
    status = "partial" if contributions else "not_assessed"
    label = "requires_review" if contributions else "not_assessed"
    reason = blocked_reason or (
        "Required assessments unavailable: " + ", ".join(key.replace("_", " ") for key in missing) + "."
        if missing else "No eligible feature assessments are available."
    )
    if contributions and not (blocked_reason or missing):
        value = fsum(contributions.values())
        status = "assessed" if len(contributions) == len(policy["weights"]) else "partial"
        label = (
            "propaganda" if value >= policy["propaganda_threshold"]
            else "suspicious" if value >= policy["review_threshold"] else "not_suspicious"
        )
        drivers = [key.replace("_", " ") for key in sorted(contributions, key=lambda key: -contributions[key])
                   if contributions[key] > 0][:2]
        reason = (
            f"Strongest weighted indicators: {' and '.join(drivers)}."
            if drivers else "No manipulation signals in the assessed features."
        )
        if status == "partial":
            reason += f" Partial assessment ({len(contributions)}/{len(policy['weights'])} features)."
    return {
        "value": value,
        "status": status,
        "label": label,
        "reason": reason,
        "policy_version": config.policy["version"],
    }


def classify(features: dict, config, blocked: bool = False):
    assessment = material_score(
        features, config, blocked_reason="Combined material assessment requires review." if blocked else None
    )
    label = {
        "not_suspicious": "no_strong_text_indicators",
        "requires_review": "inconclusive",
        "not_assessed": "inconclusive",
    }.get(assessment["label"], assessment["label"])
    contributions = weighted_contributions(features, config.policy["weighted_scoring"]["weights"])
    elevated = label in ("suspicious", "propaganda")
    return {
        "mode": "text_only",
        "label": label,
        "weighted_score": assessment["value"],
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
