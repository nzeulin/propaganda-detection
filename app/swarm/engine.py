"""Indexed temporal matches and conservative, explainable coordination groups."""

import math
import random
import re
from collections import Counter, defaultdict, deque
from datetime import UTC, datetime
from itertools import combinations
from urllib.parse import urlsplit, urlunsplit

VERSION = "coordination-v2"
MAX_FINDINGS = 500
MAX_EVIDENCE_EPISODES = 12
TEXT_PREVIEW_LIMIT = 1200
LINK_PATTERN = re.compile(r'https?://[^\s<>"\)]+', re.IGNORECASE)


def normalized_url(value):
    """Compare destinations without fragments; never fetch a submitted URL."""
    try:
        parts = urlsplit(value.rstrip(".,;"))
        scheme, host, port = parts.scheme.lower(), parts.hostname, parts.port
        if (
            scheme not in ("http", "https")
            or not host
            or parts.username is not None
            or parts.password is not None
            or any(c.isspace() for c in value)
        ):
            return None
        host = host.lower()
        authority = f"[{host}]" if ":" in host else host
        if port is not None and (scheme, port) not in (("http", 80), ("https", 443)):
            authority += f":{port}"
        return urlunsplit((scheme, authority, parts.path or "/", parts.query, ""))
    except (ValueError, TypeError, AttributeError):
        return None


def analyze_coordination(
    nodes,
    observations,
    window_seconds=60,
    minimum_episodes=3,
    baseline_trials=8,
    cancellation=None,
    comparison_budget=500000,
):
    if window_seconds <= 0 or minimum_episodes < 1 or baseline_trials < 1 or comparison_budget < 1:
        raise ValueError("Window, episode minimum, baseline trials and comparison budget must be positive")

    def check_cancelled():
        if cancellation is not None and cancellation.is_set():
            raise RuntimeError("Coordination cancelled")

    contents = {n["id"]: n["data"] for n in nodes if n["kind"] == "content"}
    account_labels = {
        n["id"]: n["data"].get("source_id", n["id"]) for n in nodes if n["kind"] == "account"
    }
    excluded = Counter()
    invalid_urls = 0
    events = []
    for event in observations:
        check_cancelled()
        if event["action"] not in ("created", "reposted", "replied_to"):
            excluded["unsupported_action"] += 1
            continue
        if not event.get("timestamp"):
            excluded["missing_timestamp"] += 1
            continue
        try:
            parsed = datetime.fromisoformat(event["timestamp"])
            if parsed.tzinfo is None:
                raise ValueError("Timestamp has no timezone")
            timestamp = parsed.astimezone(UTC).timestamp()
        except (ValueError, TypeError, OverflowError, OSError):
            excluded["invalid_timestamp"] += 1
            continue
        content = contents.get(event["target_id"])
        if content is None:
            excluded["missing_content"] += 1
            continue
        text = content.get("text", "")
        # URL tokens must not bypass the common-destination specificity discount.
        tokens = frozenset(re.findall(r"\w+", LINK_PATTERN.sub(" ", text).casefold()))
        links = LINK_PATTERN.findall(text)
        if content.get("url"):
            links.append(content["url"])
        urls = set()
        for link in links:
            key = normalized_url(link)
            if key is None:
                invalid_urls += 1
            else:
                urls.add(key)
        if len(tokens) < 4 and not urls:
            excluded["insufficient_content"] += 1
            continue
        events.append(
            {
                **event,
                "time": timestamp,
                "tokens": tokens,
                "urls": urls,
            }
        )
    events.sort(key=lambda e: (e["time"], e["id"]))
    event_lookup = {event["id"]: event for event in events}

    def source_event(event_id):
        event = event_lookup[event_id]
        content = contents[event["target_id"]]
        text = content.get("text", "")
        return {
            "event_id": event_id,
            "account_id": event["source_id"],
            "account_label": account_labels.get(event["source_id"], event["source_id"]),
            "content_id": event["target_id"],
            "content_label": content.get("source_id", event["target_id"]),
            "timestamp": datetime.fromtimestamp(event["time"], UTC).isoformat(),
            "action": event["action"],
            "text": text[:TEXT_PREVIEW_LIMIT],
            "text_truncated": len(text) > TEXT_PREVIEW_LIMIT,
            "url": content.get("url"),
        }

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

    comparisons, exhausted = 0, False

    def episodes(records, detailed=False):
        nonlocal comparisons, exhausted
        ordered = sorted(records, key=lambda e: (e["time"], e["id"]))
        index, active, expiry, pairs = defaultdict(set), {}, deque(), defaultdict(list)
        for event in ordered:
            check_cancelled()
            while expiry and expiry[0][0] < event["time"] - window_seconds:
                _, old_id = expiry.popleft()
                old = active.pop(old_id)
                for key in old["keys"]:
                    index[key].discard(old_id)
            keys = {("word", token) for token in event["tokens"]} | {("url", u) for u in event["urls"]}
            candidates = set().union(*(index[k] for k in keys)) if keys else set()
            for candidate_id in sorted(candidates):
                check_cancelled()
                comparisons += 1
                if comparisons > comparison_budget:
                    exhausted = True
                    return pairs
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
                # Require a quiet gap between matching activity, not fixed time bins.
                same_episode = prior and event["time"] - prior[-1]["last_match_time"] <= window_seconds
                if same_episode:
                    entry = prior[-1]
                    entry["last_match_time"] = event["time"]
                    replace = strength > entry["strength"]
                else:
                    entry = {"time": event["time"], "last_match_time": event["time"], "strength": strength}
                    prior.append(entry)
                    replace = True
                if replace:
                    entry["strength"] = strength
                if detailed and replace:
                    # The supporting IDs and metrics always belong to the chosen strongest match.
                    entry.update(
                        event_ids=[other["id"], event["id"]],
                        lexical_similarity=similarity,
                        shared_urls=sorted(urls),
                        separation_seconds=event["time"] - other["time"],
                        url_weights={u: url_weight[u] for u in sorted(urls)},
                    )
            active[event["id"]] = {**event, "keys": keys}
            expiry.append((event["time"], event["id"]))
            for key in keys:
                index[key].add(event["id"])
        return pairs

    warnings = []
    for reason, label in (
        ("missing_timestamp", "missing timestamps"),
        ("invalid_timestamp", "invalid or timezone-free timestamps"),
        ("missing_content", "missing referenced content"),
        ("insufficient_content", "fewer than four distinct text tokens and no valid URL"),
    ):
        if excluded[reason]:
            warnings.append(f"Excluded {excluded[reason]} observations: {label}.")
    if invalid_urls:
        warnings.append(f"Ignored {invalid_urls} malformed or unsupported URL occurrences; no URLs were fetched.")
    account_counts = Counter(e["source_id"] for e in events)
    span = events[-1]["time"] - events[0]["time"] if events else 0
    insufficient = (
        sum(count >= minimum_episodes for count in account_counts.values()) < 2
        or span <= window_seconds * (minimum_episodes - 1)
    )
    if insufficient:
        warnings.append(
            f"Insufficient data: need at least two accounts with {minimum_episodes} eligible events each "
            f"and an observation span longer than {window_seconds * (minimum_episodes - 1):g} seconds. "
            "No negative coordination conclusion can be drawn."
        )
    observed = {} if insufficient else episodes(events, detailed=True)
    baselines = defaultdict(list)
    baseline_trials_completed = 0
    rng = random.Random(20261114)
    timestamps = [e["time"] for e in events]
    for _ in range(baseline_trials):
        check_cancelled()
        if exhausted or not observed:
            break
        shuffled = timestamps.copy()
        rng.shuffle(shuffled)
        baseline = episodes([{**e, "time": t} for e, t in zip(events, shuffled, strict=True)])
        if exhausted:
            break
        for pair in observed:
            baselines[pair].append(len(baseline[pair]))
        baseline_trials_completed += 1
    reportable = [(pair, matches) for pair, matches in observed.items() if len(matches) >= minimum_episodes]
    truncated = len(reportable) > MAX_FINDINGS
    if exhausted:
        warnings.append("Dense input exhausted the comparison budget; no strong coordination is asserted.")
    if truncated:
        warnings.append(
            f"Only {MAX_FINDINGS} of {len(reportable)} candidate pairs are returned; "
            "no strong coordination is asserted on this truncated result."
        )
    findings = []
    adjacency = defaultdict(set)
    for pair, matches in sorted(reportable, key=lambda item: (-len(item[1]), item[0]))[:MAX_FINDINGS]:
        check_cancelled()
        count = len(matches)
        baseline_max = max(baselines[pair], default=0)
        strength = sum(e["strength"] for e in matches) / count
        excess = max(0, count - baseline_max)
        score = min(1, count / minimum_episodes) * strength * excess / count
        strong = not exhausted and not truncated and excess >= 2 and score >= 0.5
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
                "episodes": [
                    {**entry, "matched_events": [source_event(event_id) for event_id in entry["event_ids"]]}
                    for entry in matches[:MAX_EVIDENCE_EPISODES]
                ],
                "evidence_truncated": count > MAX_EVIDENCE_EPISODES,
                "baseline_counts": baselines[pair],
                "baseline_max": baseline_max,
                "contributions": {
                    "mean_signal_strength": strength,
                    "recurrence_factor": min(1, count / minimum_episodes),
                    "excess_fraction": excess / count,
                },
            }
        )
    if any(f["evidence_truncated"] for f in findings):
        warnings.append(
            f"At most {MAX_EVIDENCE_EPISODES} episodes per pair are shown. Scores and counts use all episodes."
        )
    # Complete-link groups deliberately refuse weak bridges between dense groups.
    remaining = set(adjacency)
    clusters = []
    while remaining:
        check_cancelled()
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
        "status": "insufficient_data" if insufficient else "needs_review" if warnings else "complete",
        "warnings": warnings,
        "version": VERSION,
        "account_labels": {account: account_labels.get(account, account) for account in sorted(accounts)},
        "findings": findings,
        "clusters": clusters,
        "parameters": {
            "window_seconds": window_seconds,
            "lexical_jaccard": 0.85,
            "minimum_episodes": minimum_episodes,
            "baseline_trials": baseline_trials,
            "seed": 20261114,
            "semantic_embeddings": False,
            "comparison_budget": comparison_budget,
            "episode_definition": "Matching activity separated by more than window_seconds of inactivity",
            "strong_score_threshold": 0.5,
            "minimum_excess_episodes": 2,
            "max_findings": MAX_FINDINGS,
            "max_evidence_episodes": MAX_EVIDENCE_EPISODES,
            "text_preview_limit": TEXT_PREVIEW_LIMIT,
        },
        "counts": {
            "observations": len(observations),
            "eligible_events": len(events),
            "accounts": len(accounts),
            "strong_pairs": sum(f["strong"] for f in findings),
            "pair_comparisons": min(comparisons, comparison_budget),
            "baseline_trials_completed": baseline_trials_completed,
            "observation_span_seconds": span,
            "excluded_events": dict(excluded),
            "invalid_url_occurrences": invalid_urls,
            "candidate_pairs": len(reportable),
            "returned_pairs": len(findings),
        },
        "formula": (
            f"min(1, episodes/{minimum_episodes}) × mean(max(lexical, URL specificity)) "
            "× max(0, episodes − baseline_max)/episodes"
        ),
        "limitations": [
            "Coordination is not proof of bots, shared control, propaganda, or malicious intent.",
            "Timestamp shuffling preserves account event counts and global time distribution, not individual rhythms.",
            (
                f"{baseline_trials} shuffled baselines are diagnostic, not calibrated statistical significance. "
                "The score is a heuristic, not a bot probability; precision and false-positive rate are unmeasured."
            ),
            (
                "Matching requires at least four shared distinct text tokens at Jaccard ≥ 0.85, or a shared URL. "
                "URLs are excluded from lexical tokens and are not fetched. Paraphrases may be missed."
            ),
            "Unknown timestamps and likes are excluded. Complete-link clustering is conservative and may omit overlapping groups.",
        ],
    }
