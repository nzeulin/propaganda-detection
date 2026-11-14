"""Read-only agent–content projection; stored detector observations stay unchanged."""

from app.core.ingestion import canonical_id


def observed_graph(nodes, observations):
    """Port agent eligibility from perf/api-speed and project replies from source metadata."""
    nodes = {node["id"]: node for node in nodes}
    actions = {"created", "modified", "reposted", "replied_to", "liked"}
    events = [
        event
        for event in observations
        if event["action"] in actions
        and nodes.get(event["source_id"], {}).get("kind") == "account"
        and nodes.get(event["target_id"], {}).get("kind") == "content"
        and nodes[event["source_id"]]["data"].get("attribution_known", True)
    ]
    capable = {
        node["id"]
        for node in nodes.values()
        if node["kind"] == "account" and (node["data"].get("can_publish") or node["data"].get("can_edit"))
    }
    capable.update(event["source_id"] for event in events if event["action"] in ("created", "modified"))
    events = [event for event in events if event["source_id"] in capable]
    contents = {node["data"]["source_id"]: node for node in nodes.values() if node["kind"] == "content"}
    replies = {
        (event["source_id"], event["target_id"], event["timestamp"])
        for event in events
        if event["action"] == "replied_to"
    }
    for content in contents.values():
        record = content["data"]
        author = record.get("author_id")
        parent = contents.get(record.get("reply_to_content_id"))
        if (
            author not in capable
            or not nodes[author]["data"].get("attribution_known", True)
            or parent is None
            or (author, parent["id"], record.get("created_at")) in replies
        ):
            continue
        events.append(
            {
                "id": canonical_id(content["id"], "replied_to", parent["id"]),
                "dataset_id": content["dataset_id"],
                "source_id": author,
                "target_id": parent["id"],
                "action": "replied_to",
                "timestamp": record.get("created_at"),
                "data": {"reply_content_id": content["id"], "observed_reply_to": record["reply_to_content_id"]},
            }
        )
    agents = {event["source_id"] for event in events}
    return [node for node in nodes.values() if node["kind"] == "content" or node["id"] in agents], events
