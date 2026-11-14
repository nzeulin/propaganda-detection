"""Response-only indicator scores; saved assessments and provider caches stay unchanged."""

from math import fsum


def feature_score(features, weights, config, *, statement=False, blocked_reason=None):
    """Normalize over assessed dimensions, retaining real zeroes and marking partial evidence."""
    available = {key: features[key] for key in weights if features.get(key) is not None}
    value, status, label = None, "not_assessed", "not_assessed"
    reason = blocked_reason or "No eligible feature assessments are available."
    if available and not blocked_reason:
        total = fsum(weights[key] for key in available)
        contributions = {key: weights[key] * score / total for key, score in available.items()}
        value = fsum(contributions.values())
        status = "assessed" if len(available) == len(weights) else "partial"
        if status == "assessed" and value >= config.policy["strong_threshold"]:
            label = "propaganda"
        elif (statement and max(available.values()) >= config.policy["indicator_threshold"]) or (
            status == "assessed" and value >= config.policy["indicator_threshold"]
        ):
            label = "suspicious"
        else:
            label = "requires_review" if status == "partial" else "not_suspicious"
        drivers = sorted(contributions, key=lambda key: -contributions[key])
        drivers = [key.replace("_", " ") for key in drivers if contributions[key] > 0][:2]
        reason = (
            f"Strongest weighted indicators: {' and '.join(drivers)}."
            if drivers else "No manipulation signals in the assessed features."
        )
        if status == "partial":
            reason = reason[:-1] + f"; partial assessment ({len(available)}/{len(weights)} features)."
    return {
        "value": value,
        "status": status,
        "label": label,
        "reason": reason,
        "policy_version": config.explicit_scores["version"],
    }


def with_explicit_scores(result, config):
    """Enrich /analyze responses without mutating cached jobs, features or statement weights."""
    weights = config.explicit_scores["weights"]
    local_weights = {key: weights[key] for key in config.statement_features}
    statements = []
    for claim in result["statements"]:
        eligible = claim["author_attributable"] and claim["stance"] == "endorsed"
        statements.append({
            **claim,
            "propaganda_score": feature_score(
                claim["features"], local_weights, config, statement=True,
                blocked_reason=None if eligible else "No author-attributable, endorsed statement evidence.",
            ),
        })
    blocked_reason = None
    if result["review_required"]:
        blocked_reason = "Combined material score withheld: narrative review required."
    elif not statements:
        blocked_reason = "No valid statements were extracted."
    return {
        **result,
        "statements": statements,
        "propaganda_score": feature_score(result["features"], weights, config, blocked_reason=blocked_reason),
    }
