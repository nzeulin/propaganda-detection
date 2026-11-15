"""Response-only indicator scores; saved assessments and provider caches stay unchanged."""

from math import fsum

from app.content.policy import classify, weighted_contributions


def feature_score(features, weights, config, *, statement=False, blocked_reason=None):
    """Normalize over assessed dimensions, retaining real zeroes and marking partial evidence."""
    contributions = weighted_contributions(features, weights)
    thresholds = config.policy if statement else config.policy["weighted_scoring"]
    review = thresholds["indicator_threshold"] if statement else thresholds["review_threshold"]
    strong = thresholds["strong_threshold"] if statement else thresholds["propaganda_threshold"]
    value, status, label = None, "not_assessed", "not_assessed"
    reason = blocked_reason or "No eligible feature assessments are available."
    if contributions and not blocked_reason:
        value = fsum(contributions.values())
        status = "assessed" if len(contributions) == len(weights) else "partial"
        if status == "assessed" and value >= strong:
            label = "propaganda"
        elif (statement and max(features[key] for key in contributions) >= review) or (
            status == "assessed" and value >= review
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
            reason = reason[:-1] + f"; partial assessment ({len(contributions)}/{len(weights)} features)."
    return {
        "value": value,
        "status": status,
        "label": label,
        "reason": reason,
        "policy_version": config.explicit_scores["version"] if statement else config.policy["version"],
    }


def with_explicit_scores(result, config):
    """Enrich /analyze responses without mutating cached jobs, features or statement weights."""
    weights = config.policy["weighted_scoring"]["weights"]
    local_weights = config.explicit_scores["statement_weights"]
    # Saved post responses zero-fill missing features; restore text evidence from its original status.
    features = {
        key: None if result["feature_details"][key]["status"] == "not_assessed" else value
        for key, value in result["features"].items()
    }
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
        "features": features,
        "statements": statements,
        "classification": classify(features, config, result["review_required"] or not statements),
        "propaganda_score": feature_score(features, weights, config, blocked_reason=blocked_reason),
    }
