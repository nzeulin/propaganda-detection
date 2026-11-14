"""Exact, symmetric mention-plus-semantic agent connections over authored material."""

import math
import re
from collections import defaultdict
from itertools import combinations

from sqlalchemy import select

from app.core.database import agent_pairs, embedding_cache
from app.core.ingestion import canonical_id
from app.core.interactions import observed_graph
from app.providers.embeddings import unit_vector


def prepare_agents(nodes, observations, policy):
    eligible, _ = observed_graph(nodes, observations)
    agents = {node["id"]: node for node in eligible if node["kind"] == "account"}
    if not agents or len(agents) > policy["max_agents"]:
        raise ValueError(f"Connectivity requires 1–{policy['max_agents']} attributed agents.")
    materials = {
        node["id"]: node for node in eligible
        if node["kind"] == "content" and node["data"].get("author_id") in agents
    }
    authored = {material["data"]["author_id"] for material in materials.values() if material["data"].get("text", "").strip()}
    missing = sorted(agents.keys() - authored)
    if missing:
        raise ValueError(f"{len(missing)} agents have no authored text. Supply text; URL-only material is not embedded.")
    return agents, {key: node for key, node in materials.items() if node["data"].get("text", "").strip()}


def collect_mentions(agents, materials, source):
    identities = defaultdict(set)
    for agent_id, agent in agents.items():
        data = agent["data"]
        for identity in (data["source_id"], data.get("handle")):
            if identity:
                identities[(data.get("platform", "unknown"), identity.casefold())].add(agent_id)
    identities = {key: next(iter(values)) for key, values in identities.items() if len(values) == 1}
    declared_ids = {(node["data"].get("platform", "unknown"), node["data"]["source_id"]): key
                    for key, node in agents.items()}
    mentions = defaultdict(list)
    originals = source.get("bluesky", {}).get("posts", {})
    for material_id, material in sorted(materials.items()):
        data = material["data"]
        author = data["author_id"]
        platform = agents[author]["data"].get("platform", "unknown")
        text = data["text"]
        targets = {}
        record = originals.get(data["source_id"], {}).get("original_record", {})
        # Facet offsets are UTF-8 byte positions, not Python character offsets.
        for facet in record.get("facets", []) if isinstance(record.get("facets", []), list) else []:
            if not isinstance(facet, dict):
                continue
            index = facet.get("index", {})
            if not isinstance(index, dict):
                continue
            start, end = index.get("byteStart"), index.get("byteEnd")
            raw = text.encode("utf-8")
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw):
                continue
            try:
                excerpt = raw[start:end].decode("utf-8")
            except UnicodeDecodeError:
                continue
            features = facet.get("features", [])
            for feature in features if isinstance(features, list) else []:
                if isinstance(feature, dict) and feature.get("$type") == "app.bsky.richtext.facet#mention":
                    identity = feature.get("did")
                    target = declared_ids.get((platform, identity)) if isinstance(identity, str) else None
                    if target:
                        targets[target] = ("platform_mention", excerpt)
        for identity in data.get("mentioned_account_ids", []) or []:
            target = declared_ids.get((platform, identity))
            if target:
                targets.setdefault(target, ("declared_mention", None))
        for match in re.finditer(r"(?<![\w@])@([\w][\w.:-]*)", text):
            target = identities.get((platform, match[1].rstrip(".").casefold()))
            if target:
                targets.setdefault(target, ("handle", match[0]))
        if platform == "bluesky":
            for match in re.finditer(r"https://bsky\.app/profile/([\w.:-]+)/?(?=[\s?#<>\"')]|$)", text):
                target = identities.get((platform, match[1].rstrip(".").casefold()))
                if target:
                    targets.setdefault(target, ("profile_url", match[0]))
        for target, (kind, excerpt) in sorted(targets.items()):
            if target != author:
                mentions[canonical_id("agent-pair", *sorted((author, target)))].append({
                    "author_id": author, "mentioned_id": target, "material_id": material_id,
                    "source": kind, "excerpt": excerpt,
                })
    return mentions


def compute_connectivity(database, job, agents, materials, embedding_info, mentions, threshold, cancellation):
    def check_cancelled():
        if cancellation.is_set():
            raise RuntimeError("Connectivity analysis cancelled.")

    keys = embedding_info["material_keys"]
    vectors, models = {}, set()
    cache_keys = sorted(set(keys.values()))
    with database.connect() as connection:
        for start in range(0, len(cache_keys), 400):
            for row in connection.execute(select(embedding_cache).where(
                embedding_cache.c.id.in_(cache_keys[start:start + 400])
            )).mappings():
                vectors[row["id"]] = unit_vector(row["vector"], embedding_info["dimensions"])
                models.add(row["model"])
    if len(models) != 1:
        raise ValueError("Agent vectors must use the same response-reported embedding model.")
    by_author = defaultdict(list)
    for material_id, material in materials.items():
        by_author[material["data"]["author_id"]].append(material_id)
    centroids = {}
    features = {}
    for author, material_ids in sorted(by_author.items()):
        check_cancelled()
        centroids[author] = unit_vector([
            math.fsum(vectors[keys[material_id]][dimension] for material_id in material_ids)
            for dimension in range(embedding_info["dimensions"])
        ], embedding_info["dimensions"])
        features[author] = {
            "material_count": len(material_ids), "material_ids": sorted(material_ids),
            "previews": [{"id": mid, "text": materials[mid]["data"]["text"][:300],
                          "url": materials[mid]["data"].get("source_post_url") or materials[mid]["data"].get("url")}
                         for mid in sorted(material_ids)[:3]],
        }
    rows = []
    adjacency = {author: set() for author in agents}
    for left, right in combinations(sorted(agents), 2):
        check_cancelled()
        pair_id = canonical_id("agent-pair", left, right)
        evidence = mentions.get(pair_id, [])
        similarity = max(0.0, min(1.0, math.fsum(a * b for a, b in zip(centroids[left], centroids[right]))))
        score = int(bool(evidence)) + similarity
        weight = max(0.0, min(1.0, (score - threshold) / (2 - threshold)))
        rows.append({"job_id": job["id"], "id": pair_id,
                     "source_id": left, "target_id": right, "mention": bool(evidence),
                     "similarity": similarity, "score": score, "weight": weight,
                     "evidence": {"total": len(evidence), "items": evidence[:20]}})
        if weight > 0:
            adjacency[left].add(right)
            adjacency[right].add(left)
    groups, seen = [], set()
    for author in sorted(agents):
        if author in seen:
            continue
        pending, members = [author], set()
        while pending:
            current = pending.pop()
            if current in members:
                continue
            members.add(current)
            pending.extend(adjacency[current] - members)
        seen.update(members)
        if len(members) >= 2:
            groups.append({"id": canonical_id("connected-group", sorted(members)), "account_ids": sorted(members)})
    check_cancelled()
    if rows:
        with database.begin() as connection:
            connection.execute(agent_pairs.insert(), rows)
    labels = {key: ("@" + node["data"]["handle"] if node["data"].get("handle") else node["data"]["source_id"])
              for key, node in agents.items()}
    return {
        "mode": "agent_connectivity", "status": "complete" if len(agents) >= 2 else "insufficient_data",
        "clusters": groups, "account_labels": labels, "agent_features": features,
        "counts": {"accounts": len(agents), "materials": len(materials), "pair_comparisons": len(rows),
                   "connected_pairs": sum(row["weight"] > 0 for row in rows),
                   "isolated_agents": sum(not neighbors for neighbors in adjacency.values())},
        "parameters": {"threshold": threshold, "model": next(iter(models)),
                       "dimensions": embedding_info["dimensions"], "version": embedding_info["version"]},
        "embedding_cache": {key: value for key, value in embedding_info.items() if key != "material_keys"},
        "formula": "binary mention + max(0, cosine of normalized authored-material averages)",
        "warnings": [], "limitations": ["Connections describe content similarity and references, not verified coordination or bot identity."],
    }
