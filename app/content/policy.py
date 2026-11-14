"""Experimental screening policy, never a calibrated truth or propaganda verdict."""


def classify(features: dict, config, blocked: bool = False):
    required = config.policy["required_features"]
    available = {k: value for k, value in features.items() if value is not None}
    moderate = [k for k, value in available.items() if value >= config.policy["indicator_threshold"]]
    strong = [k for k, value in available.items() if value >= config.policy["strong_threshold"]]
    if blocked or any(features[k] is None for k in required):
        label = "inconclusive"
    elif len(moderate) >= config.policy["minimum_dimensions"] and strong:
        label = "indicators_detected"
    else:
        label = "no_strong_text_indicators"
    return {
        "mode": "text_only",
        "label": label,
        "risk_score": None,
        "policy_version": config.policy["version"],
        "experimental": True,
        "trigger_features": moderate if label == "indicators_detected" else [],
        "strong_features": strong if label == "indicators_detected" else [],
    }
