"""Read-only agent–content projection; stored detector observations stay unchanged."""

from app.core.ingestion import canonical_id


def observed_graph(nodes, observations):
    """Include attributed interacting accounts and project collected reply/quote material."""
    nodes = {node["id"]: node for node in nodes}
    actions = {"created", "modified", "reposted", "replied_to", "liked", "quoted"}
    events = [
        event
        for event in observations
        if event["action"] in actions
        and nodes.get(event["source_id"], {}).get("kind") == "account"
        and nodes.get(event["target_id"], {}).get("kind") == "content"
        and nodes[event["source_id"]]["data"].get("attribution_known", True)
    ]
    contents = {node["data"]["source_id"]: node for node in nodes.values() if node["kind"] == "content"}
    relations = {
        (event["source_id"], event["target_id"], event["action"], event["timestamp"])
        for event in events
        if event["action"] in {"replied_to", "quoted"}
    }
    for content in contents.values():
        record = content["data"]
        author = record.get("author_id")
        if author not in nodes or not nodes[author]["data"].get("attribution_known", True):
            continue
        for action, field in (("replied_to", "reply_to_content_id"), ("quoted", "quote_to_content_id")):
            parent = contents.get(record.get(field))
            if parent is None or (author, parent["id"], action, record.get("created_at")) in relations:
                continue
            events.append({
                "id": canonical_id(content["id"], action, parent["id"]),
                "dataset_id": content["dataset_id"],
                "source_id": author,
                "target_id": parent["id"],
                "action": action,
                "timestamp": record.get("created_at"),
                "data": {"response_content_id": content["id"],
                         **({"reply_content_id": content["id"], "observed_reply_to": record[field]}
                            if action == "replied_to" else {"observed_quote_to": record[field]})},
            })
    agents = {event["source_id"] for event in events}
    return [node for node in nodes.values() if node["kind"] == "content" or node["id"] in agents], events
