"""One-hop public interaction discovery and bounded authored-post enrichment."""

from collections import Counter
from itertools import zip_longest
from time import monotonic

from pydantic import ValidationError

from app.core.ingestion import ImportRow
from app.swarm.bluesky import CollectionError, _check_cancelled, _read_json, normalize_authored_post


def discover_interactions(client, rows, sources, *, deadline, cancellation=None):
    """Mutate the collected snapshot only; added posts never become discovery seeds."""
    ordered = sorted(rows, key=lambda row: (row["timestamp"], row["content_id"]), reverse=True)
    explicit = [row for row in ordered if sources[row["content_id"]].get("requested_post_urls")]
    seeds = list({row["content_id"]: row for row in explicit + ordered}.values())[:10]
    known = {row["account_id"] for row in rows}
    profiles, buffers, coverage, failures = {}, [], [], []
    skipped = Counter()
    report = {
        "seed_post_ids": [row["content_id"] for row in seeds], "seed_limit": 10,
        "new_user_limit": 50, "recent_posts_per_user": 5, "interaction_page_limit": 1,
        "interaction_record_limit": 50, "recent_feed_page_limit": 2,
        "omitted_seed_posts": len(rows) - len(seeds), "api_requests": 0,
        "coverage": coverage, "failures": failures, "budget_exhausted": False,
    }

    def fetch(method, params):
        _check_cancelled(cancellation)
        if monotonic() >= deadline:
            report["budget_exhausted"] = True
            return None
        report["api_requests"] += 1
        try:
            return _read_json(client, method, params, cancellation=cancellation, deadline=deadline)
        except CollectionError as exc:
            _check_cancelled(cancellation)
            report["budget_exhausted"] = monotonic() >= deadline
            failures.append({"method": method, "subject": params.get("uri", params.get("actor")), "error": str(exc)})
            return None

    for seed in seeds:
        uri = seed["content_id"]
        for action, method, key in (
            ("replied_to", "getPostThread", "thread"),
            ("quoted", "getQuotes", "posts"),
            ("reposted", "getRepostedBy", "repostedBy"),
            ("liked", "getLikes", "likes"),
        ):
            params = {"uri": uri, **({"depth": 1, "parentHeight": 0} if key == "thread" else {"limit": 50})}
            data = fetch(f"app.bsky.feed.{method}", params)
            status = {"seed_post_id": uri, "action": action, "received": 0, "truncated": False,
                      "status": "budget_exhausted" if report["budget_exhausted"] else "failed"}
            coverage.append(status)
            batch = []
            buffers.append(batch)
            if data is None:
                continue
            entries = data.get(key)
            if key == "thread":
                if not isinstance(entries, dict) or entries.get("$type") != "app.bsky.feed.defs#threadViewPost":
                    status["status"] = "unavailable"
                    continue
                thread_post = entries.get("post", {})
                if not isinstance(thread_post, dict) or thread_post.get("uri") != uri:
                    status["status"] = "invalid_response"
                    continue
                entries = entries.get("replies", [])
            elif data.get("uri") != uri:
                status["status"] = "invalid_response"
                continue
            if not isinstance(entries, list):
                status["status"] = "invalid_response"
                continue
            status.update(status="collected", received=len(entries), truncated=bool(data.get("cursor")) or len(entries) > 50)
            if key == "thread":
                reply_count = thread_post.get("replyCount")
                status["truncated"] |= isinstance(reply_count, int) and reply_count > len(entries)
            for entry in entries[:50]:
                if not isinstance(entry, dict):
                    skipped["malformed_interaction"] += 1
                    continue
                post = entry.get("post") if key == "thread" else entry if action == "quoted" else None
                actor = post.get("author") if isinstance(post, dict) else entry.get("actor") if action == "liked" else entry
                if not isinstance(actor, dict) or not isinstance(actor.get("did"), str):
                    skipped["missing_actor"] += 1
                    continue
                did = actor["did"]
                if not did.startswith("did:") or len(did) > 200:
                    skipped["invalid_actor"] += 1
                    continue
                authored, source = None, None
                timestamp = entry.get("createdAt") if action == "liked" else None
                if action in ("quoted", "replied_to"):
                    if not isinstance(post, dict) or not isinstance(post.get("record"), dict):
                        skipped["unavailable_response_post"] += 1
                        continue
                    record = post["record"]
                    if action == "replied_to":
                        reply = record.get("reply", {})
                        target = reply.get("parent", {}) if isinstance(reply, dict) else {}
                    else:
                        embed = record.get("embed", {})
                        target = embed.get("record", {}) if isinstance(embed, dict) else {}
                        if isinstance(target, dict) and "record" in target:
                            target = target["record"]
                    if not isinstance(target, dict) or target.get("uri") != uri:
                        skipped["unrelated_response_post"] += 1
                        continue
                    authored, source, reason = normalize_authored_post({"post": post}, did)
                    if reason:
                        skipped[reason] += 1
                    timestamp = record.get("createdAt")
                try:
                    event = ImportRow(account_id=did, content_id=uri, action=action,
                                      timestamp=timestamp, platform="bluesky").model_dump(exclude_none=True)
                except (ValidationError, ValueError, OverflowError):
                    skipped["invalid_interaction_fields"] += 1
                    continue
                batch.append({"row": event, "post": authored, "source": source, "evidence": entry,
                              "response_content_id": post.get("uri") if isinstance(post, dict) else None})
                handle = actor.get("handle")
                profiles.setdefault(did, {"did": did, "handle": handle if isinstance(handle, str) else None, "origins": []})

    # Round-robin selection prevents the first popular post or action consuming the user budget.
    discovered = {}
    for group in zip_longest(*buffers):
        for candidate in group:
            if candidate is None:
                continue
            did = candidate["row"]["account_id"]
            if did not in known and did not in discovered and len(discovered) < 50:
                discovered[did] = profiles[did]
    selected = known | discovered.keys()
    interactions, event_keys = [], set()

    def add_post(row, source, origin):
        uri = row["content_id"]
        if uri not in sources:
            if len(rows) >= 5000:
                skipped["event_limit"] += 1
                return False
            rows.append(row)
            sources[uri] = source
        origins = sources[uri].setdefault("discovery_origins", [])
        if origin not in origins:
            origins.append(origin)
        return True

    for batch in buffers:
        for item in batch:
            event = item["row"]
            did = event["account_id"]
            if did not in selected:
                continue
            origin = {"seed_post_id": event["content_id"], "action": event["action"]}
            needed = 1 + int(item["post"] is not None and item["post"]["content_id"] not in sources)
            if len(rows) + needed > 5000:
                skipped["event_limit"] += 1
                continue
            if item["post"]:
                add_post(item["post"], item["source"], origin)
            event_key = (did, event["content_id"], event["action"], event.get("timestamp"))
            if event_key not in event_keys and len(rows) < 5000:
                rows.append(event)
                event_keys.add(event_key)
                interactions.append({**event, "response_content_id": item["response_content_id"],
                                     "original": item["evidence"]})
                if origin not in profiles[did]["origins"]:
                    profiles[did]["origins"].append(origin)

    discovered = {did: profile for did, profile in discovered.items() if profile["origins"]}
    retained = known | discovered.keys()
    # A separate bounded feed pass enriches users, never the discovery seed list.
    for did, profile in discovered.items():
        cursor, used_cursors, recent = None, set(), set()
        profile.update(posts_collected=0, pages=0, stop_reason="page_limit", source_type="discovered")
        for _ in range(2):
            if len(rows) >= 5000:
                profile["stop_reason"] = "event_limit"
                break
            params = {"actor": did, "filter": "posts_no_replies", "includePins": "false", "limit": 25}
            if cursor:
                params["cursor"] = cursor
            data = fetch("app.bsky.feed.getAuthorFeed", params)
            if data is None:
                profile["stop_reason"] = "budget_exhausted" if report["budget_exhausted"] else "failed"
                break
            feed = data.get("feed")
            if not isinstance(feed, list):
                profile["stop_reason"] = "invalid_response"
                break
            profile["pages"] += 1
            for entry in feed[:25]:
                reason = entry.get("reason") if isinstance(entry, dict) else None
                if isinstance(reason, dict) and reason.get("$type") == "app.bsky.feed.defs#reasonPin":
                    continue
                row, source, reason = normalize_authored_post(entry, did)
                if reason:
                    skipped[reason] += 1
                    continue
                if add_post(row, source, {"account_did": did, "kind": "recent_authored_post"}):
                    recent.add(row["content_id"])
                if len(recent) >= 5 or len(rows) >= 5000:
                    break
            profile["posts_collected"] = len(recent)
            next_cursor = data.get("cursor")
            if len(recent) >= 5 or len(rows) >= 5000:
                profile["stop_reason"] = "post_limit" if len(recent) >= 5 else "event_limit"
                break
            if not feed or not next_cursor:
                profile["stop_reason"] = "feed_exhausted"
                break
            if not isinstance(next_cursor, str) or next_cursor in used_cursors:
                profile["stop_reason"] = "repeated_or_invalid_cursor"
                break
            used_cursors.add(next_cursor)
            cursor = next_cursor
    _check_cancelled(cancellation)
    report.update(new_users=len(discovered), omitted_users=len(profiles.keys() - retained),
                  interaction_count=len(interactions), skipped_entries=dict(skipped))
    return report, list(discovered.values()), interactions
