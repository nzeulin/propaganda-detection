from datetime import UTC, datetime, timedelta

import pytest

from app.swarm.engine import analyze_coordination, normalized_url


def repeated_posts():
    accounts = ("account-a", "account-b")
    nodes = [
        {"id": account, "kind": "account", "data": {"source_id": account}}
        for account in accounts
    ]
    observations = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    text = "Residents gather beside the river and demand clear answers today."
    for episode in range(3):
        for offset, account in enumerate(accounts):
            event_id = f"event-{episode}-{account}"
            content_id = f"content-{episode}-{account}"
            timestamp = start + timedelta(seconds=episode * 120 + offset)
            nodes.append(
                {"id": content_id, "kind": "content", "data": {"text": text}}
            )
            observations.append(
                {
                    "id": event_id,
                    "source_id": account,
                    "target_id": content_id,
                    "action": "created",
                    "timestamp": timestamp.isoformat(),
                }
            )
    return nodes, observations


def test_repeated_cross_account_matches_are_reported_with_evidence():
    nodes, observations = repeated_posts()

    result = analyze_coordination(nodes, observations, baseline_trials=2)

    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert (finding["source_id"], finding["target_id"]) == ("account-a", "account-b")
    assert finding["episode_count"] == 3
    assert len(finding["episodes"]) == 3
    assert all(len(episode["matched_events"]) == 2 for episode in finding["episodes"])


def test_missing_timestamps_are_excluded_and_result_abstains():
    nodes, observations = repeated_posts()
    observations = [{key: value for key, value in row.items() if key != "timestamp"} for row in observations]

    result = analyze_coordination(nodes, observations, baseline_trials=2)

    assert result["status"] == "insufficient_data"
    assert result["findings"] == []
    assert result["counts"]["excluded_events"]["missing_timestamp"] == 6
    assert any(
        "no negative coordination conclusion" in warning.casefold()
        for warning in result["warnings"]
    )


def test_comparison_budget_exhaustion_never_asserts_strong_coordination():
    nodes, observations = repeated_posts()

    result = analyze_coordination(nodes, observations, comparison_budget=1)

    assert result["counts"]["pair_comparisons"] == 1
    assert result["findings"] == []
    assert any("no strong coordination is asserted" in warning for warning in result["warnings"])


def test_invalid_analysis_parameters_are_rejected():
    with pytest.raises(ValueError, match="must be positive"):
        analyze_coordination([], [], window_seconds=0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HTTPS://Example.COM:443/news?id=1#section", "https://example.com/news?id=1"),
        ("http://example.com:80", "http://example.com/"),
        ("https://user:password@example.com/news", None),
        ("http://example.com:not-a-port/news", None),
    ],
)
def test_normalized_url(value, expected):
    assert normalized_url(value) == expected
