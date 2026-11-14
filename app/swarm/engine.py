"""Indexed temporal matches and conservative, explainable coordination groups."""

import math
import random
import re
from collections import defaultdict, deque
from datetime import datetime
from itertools import combinations
from urllib.parse import urlsplit, urlunsplit


def analyze_coordination(nodes, observations, window_seconds=60, minimum_episodes=3, baseline_trials=8):
    contents = {n["id"]: n["data"] for n in nodes if n["kind"] == "content"}
    events = []
    for event in observations:
        if not event["timestamp"] or event["action"] == "liked":
            continue
        content = contents.get(event["target_id"], {})
        text = content.get("text", "")
        tokens = frozenset(re.findall(r"\w+", text.casefold()))
        links = re.findall(r'https?://[^\s<>"\)]+', text)
        if content.get("url"):
            links.append(content["url"])
        urls = set()
        for link in links:
            parts = urlsplit(link.rstrip(".,;"))
            if parts.scheme in ("http", "https") and parts.hostname:
                urls.add(urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, "")))
        events.append(
            {
                **event,
                "time": datetime.fromisoformat(event["timestamp"]).timestamp(),
                "tokens": tokens,
                "urls": urls,
            }
        )
    url_accounts = defaultdict(set)
    for event in events:
        for url in event["urls"]:
            url_accounts[url].add(event["source_id"])
    accounts = {e["source_id"] for e in events}
    url_weight = (
        {
            url: math.log((1 + len(accounts)) / len(users)) / math.log(1 + len(accounts))
            for url, users in url_accounts.items()
        }
        if accounts
        else {}
    )

    def episodes(records, detailed=False):
        ordered = sorted(records, key=lambda e: (e["time"], e["id"]))
        index, active, expiry, pairs = defaultdict(set), {}, deque(), defaultdict(list)
        for event in ordered:
            while expiry and expiry[0][0] < event["time"] - window_seconds:
                _, old_id = expiry.popleft()
                old = active.pop(old_id)
                for key in old["keys"]:
                    index[key].discard(old_id)
            keys = {("word", token) for token in event["tokens"]} | {("url", u) for u in event["urls"]}
            candidates = set().union(*(index[k] for k in keys)) if keys else set()
            for candidate_id in candidates:
                other = active[candidate_id]
                if other["source_id"] == event["source_id"]:
                    continue
                shared = event["tokens"] & other["tokens"]
                union = event["tokens"] | other["tokens"]
                similarity = len(shared) / len(union) if union and len(shared) >= 4 else 0
                urls = event["urls"] & other["urls"]
                if similarity < 0.85 and not urls:
                    continue
                strength = max(
                    similarity if similarity >= 0.85 else 0, max((url_weight[u] for u in urls), default=0)
                )
                pair = tuple(sorted((event["source_id"], other["source_id"])))
                prior = pairs[pair]
                # A burst counts once; text and URL signals cannot multiply that episode.
                if prior and event["time"] - prior[-1]["time"] <= window_seconds:
                    prior[-1]["strength"] = max(prior[-1]["strength"], strength)
                    continue
                entry = {"time": event["time"], "strength": strength}
                if detailed:
                    entry.update(
                        event_ids=[other["id"], event["id"]],
                        lexical_similarity=similarity,
                        shared_urls=sorted(urls),
                        separation_seconds=event["time"] - other["time"],
                        url_weights={u: url_weight[u] for u in sorted(urls)},
                    )
                prior.append(entry)
            active[event["id"]] = {**event, "keys": keys}
            expiry.append((event["time"], event["id"]))
            for key in keys:
                index[key].add(event["id"])
        return pairs

    observed = episodes(events, detailed=True)
    baselines = defaultdict(list)
    rng = random.Random(20261114)
    timestamps = [e["time"] for e in events]
    for _ in range(baseline_trials):
        shuffled = timestamps.copy()
        rng.shuffle(shuffled)
        baseline = episodes([{**e, "time": t} for e, t in zip(events, shuffled, strict=True)])
        for pair in observed:
            baselines[pair].append(len(baseline[pair]))
    findings = []
    adjacency = defaultdict(set)
    for pair, matches in sorted(observed.items()):
        count = len(matches)
        baseline_max = max(baselines[pair], default=0)
        strength = sum(e["strength"] for e in matches) / count
        excess = max(0, count - baseline_max)
        score = min(1, count / minimum_episodes) * strength * excess / count
        strong = count >= minimum_episodes and excess >= 2 and score >= 0.5
        if strong:
            adjacency[pair[0]].add(pair[1])
            adjacency[pair[1]].add(pair[0])
        findings.append(
            {
                "id": "coordination:" + ":".join(pair),
                "source_id": pair[0],
                "target_id": pair[1],
                "action": "suspicious_coordination",
                "inferred": True,
                "score": score,
                "strong": strong,
                "episode_count": count,
                "episodes": matches,
                "baseline_counts": baselines[pair],
                "baseline_max": baseline_max,
                "contributions": {
                    "mean_signal_strength": strength,
                    "recurrence_factor": min(1, count / minimum_episodes),
                    "excess_fraction": excess / count,
                },
            }
        )
    # Complete-link groups deliberately refuse weak bridges between dense groups.
    remaining = set(adjacency)
    clusters = []
    while remaining:
        seed = min(remaining, key=lambda n: (-len(adjacency[n] & remaining), n))
        group = [seed]
        for candidate in sorted(adjacency[seed] & remaining, key=lambda n: (-len(adjacency[n]), n)):
            if all(candidate in adjacency[member] for member in group):
                group.append(candidate)
        remaining.difference_update(group)
        if len(group) >= 3:
            links = sum(b in adjacency[a] for a, b in combinations(group, 2))
            clusters.append(
                {
                    "id": f"cluster-{len(clusters) + 1}",
                    "account_ids": group,
                    "density": links / (len(group) * (len(group) - 1) / 2),
                }
            )
    return {
        "version": "coordination-v1",
        "findings": findings,
        "clusters": clusters,
        "parameters": {
            "window_seconds": window_seconds,
            "lexical_jaccard": 0.85,
            "minimum_episodes": minimum_episodes,
            "baseline_trials": baseline_trials,
            "seed": 20261114,
            "semantic_embeddings": False,
        },
        "counts": {
            "observations": len(observations),
            "eligible_events": len(events),
            "accounts": len(accounts),
            "strong_pairs": sum(f["strong"] for f in findings),
        },
        "formula": "min(1, episodes/3) × mean(max(lexical, URL specificity)) × max(0, episodes − baseline_max)/episodes",
        "limitations": [
            "Coordination is not proof of bots, shared control, propaganda, or malicious intent.",
            "Timestamp shuffling preserves account event counts and global time distribution, not individual rhythms.",
            "Eight shuffled baselines are a diagnostic comparison, not calibrated statistical significance.",
            "Unknown timestamps and likes are excluded. Complete-link clustering is conservative and may omit overlapping groups.",
        ],
    }
