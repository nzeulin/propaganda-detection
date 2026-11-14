"""Small, explicitly synthetic inputs for exercising the real coordination engine."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def swarm_examples():
    # Reuse the checked-in network so file upload and the dropdown tell the same story.
    coordinated = json.loads(
        (Path(__file__).resolve().parents[2] / "data" / "demo_network.json").read_text(encoding="utf-8")
    )
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    benign = []
    messages = [
        "The north library opens registration for the reading programme today.",
        "South branch readers can now register for our summer book sessions.",
        "East library families are invited to join this year's reading challenge.",
        "West branch is accepting applications for the children's book programme.",
    ]
    for index, message in enumerate(messages):
        benign.append(
            {
                "account_id": f"library-branch-{index + 1}",
                "content_id": f"library-launch-{index + 1}",
                "action": "created",
                "timestamp": (start + timedelta(seconds=index * 2)).isoformat(),
                "text": message,
                "url": "https://library.example/summer-reading",
                "platform": "synthetic",
            }
        )
        for update in range(3):
            benign.append(
                {
                    "account_id": f"library-branch-{index + 1}",
                    "content_id": f"branch-{index + 1}-update-{update}",
                    "action": "created",
                    "timestamp": (start + timedelta(hours=update + 1, minutes=index * 7)).isoformat(),
                    "text": f"Branch {index + 1} update {update}: {message}",
                    "platform": "synthetic",
                }
            )
    missing = [
        {
            "account_id": f"unknown-time-{account}",
            "content_id": f"unknown-time-{account}-{post}",
            "action": "created",
            "text": "A shared community update with no recorded posting time.",
            "platform": "synthetic",
        }
        for account in range(2)
        for post in range(3)
    ]
    return [
        {
            "id": "coordinated-network",
            "name": "Synthetic coordinated network",
            "description": (
                "26 fictional accounts and 172 posts: two groups of three repeat synchronized messages "
                "across 12 rounds, alongside 20 background accounts. Deliberately easy test, not a benchmark."
            ),
            "synthetic": True,
            "rows": coordinated,
        },
        {
            "id": "benign-announcement",
            "name": "Synthetic library announcement (benign contrast)",
            "description": (
                "Four fictional library branches share one launch URL within six seconds, followed by "
                "separate updates. One synchronized announcement should not establish recurrent coordination. "
                "Legitimate campaigns with recurring synchrony can still be flagged; intent is not inferred."
            ),
            "synthetic": True,
            "rows": benign,
        },
        {
            "id": "missing-timestamps",
            "name": "Synthetic missing timestamps (insufficient data)",
            "description": "Two fictional accounts repeat text without timestamps. The result must abstain.",
            "synthetic": True,
            "rows": missing,
        },
    ]