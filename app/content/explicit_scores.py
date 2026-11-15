"""Response-only indicator scores; saved assessments and provider caches stay unchanged."""

from math import fsum

from app.content.policy import assessed_features, classify, material_score, weighted_contributions


def feature_score(features, weights, config, *, statement=False, blocked_reason=None):
    """Normalize over assessed dimensions, retaining real zeroes and marking partial evidence."""
    if not statement:
        return material_score(features, config, blocked_reason=blocked_reason)
    contributions = weighted_contributions(features, weights)
    review = config.policy["indicator_threshold"]
    strong = config.policy["strong_threshold"]
    value, status, label = None, "not_assessed", "not_assessed"
    reason = blocked_reason or "No eligible feature assessments are available."
    if contributions and not blocked_reason:
        value = fsum(contributions.values())
        status = "assessed" if len(contributions) == len(weights) else "partial"
        if status == "assessed" and value >= strong:
            label = "propaganda"
        elif max(features[key] for key in contributions) >= review:
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
        "policy_version": config.explicit_scores["version"],
    }


def with_explicit_scores(result, config):
    """Enrich /analyze responses without mutating cached jobs, features or statement weights."""
    weights = config.policy["weighted_scoring"]["weights"]
    local_weights = config.explicit_scores["statement_weights"]
    features = assessed_features(result)
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
