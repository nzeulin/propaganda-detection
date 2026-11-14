"""Explicit missingness, denominators, split balance and leakage diagnostics."""

import hashlib
import re
from collections import Counter, defaultdict


def audit_corpus(records):
    splits, labels, groups, hashes, evidence_groups = (
        Counter(),
        Counter(),
        defaultdict(set),
        defaultdict(list),
        defaultdict(set),
    )
    shingles, index, near = [], defaultdict(list), []
    for record in records:
        splits[record["split"]] += 1
        labels[(record["split"], record["reference_annotation"]["dominant_family"])] += 1
        groups[record["scenario_id"]].add(record["split"])
        tokens = re.findall(r"\w+", record["text"].casefold())
        digest = hashlib.sha256(" ".join(tokens).encode()).hexdigest()
        hashes[digest].append(record["id"])
        evidence = record.get("reference_facts", "").strip()
        if evidence:
            evidence_groups[hashlib.sha256(evidence.encode()).hexdigest()].add(record["split"])
        grams = {tuple(tokens[i : i + 4]) for i in range(len(tokens) - 3)}
        candidates = Counter(other for gram in grams for other in index[gram])
        for other, common in candidates.items():
            if record["split"] == records[other]["split"]:
                continue
            union = len(grams) + len(shingles[other]) - common
            if union and common / union >= 0.8:
                near.append({"ids": [records[other]["id"], record["id"]], "jaccard": common / union})
        for gram in grams:
            index[gram].append(len(shingles))
        shingles.append(grams)
    duplicates = [ids for ids in hashes.values() if len(ids) > 1]
    cross_groups = [key for key, values in groups.items() if len(values) > 1]
    cross_evidence = [key for key, values in evidence_groups.items() if len(values) > 1]
    return {
        "records": len(records),
        "splits": dict(splits),
        "labels": [
            {"split": split, "label": label, "count": count}
            for (split, label), count in sorted(labels.items())
        ],
        "exact_duplicates": duplicates,
        "cross_split_near_duplicates": near,
        "cross_split_scenarios": cross_groups,
        "cross_split_identical_evidence": cross_evidence,
        "leakage_checks_pass": not (duplicates or near or cross_groups or cross_evidence),
    }


def evaluate_predictions(records, predictions, features):
    by_id = {r["id"]: r for r in records}
    family_metrics = {f: Counter() for f in features}
    confusion = Counter()
    errors, latency, coverage, escalation = [], [], [], []
    for record_id, prediction in predictions.items():
        if record_id not in by_id:
            continue
        reference = by_id[record_id]["reference_annotation"]
        if reference["dominant_family"] == "uncertain":
            continue
        result = prediction["result"]
        truth = reference["dominant_family"] != "none"
        label = result["classification"]["label"]
        verdict = None if label == "inconclusive" else label == "indicators_detected"
        confusion[
            "abstained"
            if verdict is None
            else "tp"
            if truth and verdict
            else "fn"
            if truth
            else "fp"
            if verdict
            else "tn"
        ] += 1
        expected = set(reference["secondary_families"]) | {reference["dominant_family"]}
        for feature in features:
            value = result["features"][feature]
            key = (
                "abstained"
                if value is None
                else ("tp" if feature in expected else "fp")
                if value >= 0.5
                else ("fn" if feature in expected else "tn")
            )
            family_metrics[feature][key] += 1
        if verdict is None or truth != verdict:
            errors.append(
                {
                    "id": record_id,
                    "reference": reference["dominant_family"],
                    "prediction": label,
                    "type": "abstention"
                    if verdict is None
                    else "false_negative"
                    if truth
                    else "false_positive",
                }
            )
        latency.append(prediction["seconds"])
        coverage.append(sum(result["coverage"].values()) / len(features))
        escalation.append(bool(result.get("verification", {}).get("escalated")))
    families = {}
    for feature, counts in family_metrics.items():
        precision = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else None
        recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else None
        families[feature] = {
            **{k: counts[k] for k in ("tp", "fp", "tn", "fn", "abstained")},
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None,
        }
    total = sum(confusion.values())
    return {
        "evaluated": total,
        "confusion": {k: confusion[k] for k in ("tp", "fp", "tn", "fn", "abstained")},
        "families": families,
        "negative_false_positive_rate": confusion["fp"] / (confusion["fp"] + confusion["tn"])
        if confusion["fp"] + confusion["tn"]
        else None,
        "abstention_rate": confusion["abstained"] / total if total else None,
        "mean_coverage": sum(coverage) / len(coverage) if coverage else None,
        "escalation_rate": sum(escalation) / len(escalation) if escalation else None,
        "mean_seconds": sum(latency) / len(latency) if latency else None,
        "errors": errors,
        "denominators": "Precision/recall/FPR use assessed cases; abstentions are reported separately. Uncertain references are excluded.",
        "reference_type": "AI-assisted reference annotations, not human gold",
    }
