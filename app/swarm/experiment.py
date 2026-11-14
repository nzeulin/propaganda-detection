"""Offline, fixed-input Bluesky cohort comparisons; never collect or alter posts.

Run with ``python -m app.swarm.experiment --plan <plan.json> --output-dir <new-dir>``.
Plans name already collected snapshot directories and predeclared UTC boundaries.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from app.core.ingestion import DatasetInput, prepare_dataset
from app.swarm.bluesky import normalize_authored_post
from app.swarm.engine import VERSION, analyze_coordination

WINDOWS = (60, 300, 900)
LIMITATIONS = [
    "A common date filter is not complete common coverage: feed and post caps leave gaps.",
    "Selected accounts are not a platform-wide or keyword-filtered sample; no independent labels are available.",
    "Only authored posts are included. Repost wrappers and reply relationships are not reconstructed.",
    ("Comparisons include indexed candidate evaluations, same-account candidates and shuffled trials; "
     "they are not a count of matching posts or independent pairs."),
    "Wider windows also merge nearby matches into longer episodes; outcomes need not grow monotonically.",
    "Coordination is not proof of bots, shared control or malicious intent. Scores are not probabilities.",
    "Eight shuffled trials are diagnostics, not calibrated statistical significance or an accuracy benchmark.",
]


def utc_boundary(value):
    """Require explicit offsets; do not silently interpret local or naive time."""
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("Missing timezone")
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Date boundaries require an in-range ISO timestamp with a timezone") from exc


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def compare_snapshot(rows, provenance, *, since, until, windows=WINDOWS):
    """Validate provenance, slice [since, until), compare identical unmodified rows.

    Provenance consistency is not independent proof of authenticity. Live-source
    verification is a separate step, and no known bot labels are inferred here.
    """
    start, end = utc_boundary(since), utc_boundary(until)
    if start >= end:
        raise ValueError("since must be earlier than until")
    if not windows or len(windows) > 3 or len(set(windows)) != len(windows) or any(
        type(window) is not int or window not in WINDOWS for window in windows
    ):
        raise ValueError("Choose distinct comparison windows from 60, 300 and 900 seconds")
    collection, sources = provenance["collection"], provenance["posts"]
    if collection.get("synthetic") is not False or collection.get("post_count") != len(rows):
        raise ValueError("Snapshot must be marked non-synthetic with a matching row count")
    # Enforce the import size/row limits on the *whole* snapshot, not just its slice.
    prepare_dataset(DatasetInput(name="Collected Bluesky snapshot", rows=rows))
    seen, selected = set(), []
    for row in rows:
        uri = row["content_id"]
        if uri in seen:
            raise ValueError("Duplicate source post URI in snapshot")
        seen.add(uri)
        source = sources.get(uri)
        if source is None:
            raise ValueError("Missing source provenance")
        if not isinstance(source, dict):
            raise TypeError("Source provenance must be an object")
        recreated, expected, reason = normalize_authored_post({"post": {
            "uri": uri, "author": {"did": source.get("account_did"),
                                     "handle": source.get("author_handle_at_collection")},
            "record": source.get("original_record"), "cid": source.get("post_cid"),
            "indexedAt": source.get("source_indexed_at"),
        }}, row["account_id"])
        if reason or recreated != row or any(
            source.get(key) != expected[key]
            for key in ("content_id", "post_created_at", "source_post_url", "record_sha256", "structured_urls")
        ):
            raise ValueError("Post row or provenance does not match the saved original record")
        if start <= utc_boundary(row["timestamp"]) < end:
            selected.append(row)
    selected.sort(key=lambda row: (row["timestamp"], row["content_id"]))
    if selected:
        dataset_id, _, nodes, observations = prepare_dataset(DatasetInput(
            name="Bluesky shared-date cohort", rows=selected,
        ))
    else:
        dataset_id, nodes, observations = None, [], []
    analyses = {
        str(window): analyze_coordination(nodes, observations, window_seconds=window)
        for window in windows
    }
    selected_counts = Counter(row["account_id"] for row in selected)
    coverage = [{
        "handle": account["handle"], "did": account["did"],
        "collected_posts": account["posts_collected"],
        "selected_posts": selected_counts[account["did"]],
        "oldest_collected_utc": account["oldest_post_utc"],
        "newest_collected_utc": account["newest_post_utc"],
        "stop_reason": account["stop_reason"],
        "collected_oldest_at_or_before_start": bool(
            account["oldest_post_utc"] and utc_boundary(account["oldest_post_utc"]) <= start
        ),
    } for account in collection["accounts"] if "handle" in account]
    summary = {
        "since_inclusive": start.isoformat(), "until_exclusive": end.isoformat(),
        "collected_posts": len(rows), "selected_posts": len(selected),
        "outside_range_posts": len(rows) - len(selected),
        "accounts_with_selected_posts": len(selected_counts), "coverage": coverage,
        "rows_sha256_canonical": digest(selected), "source_rows_sha256_canonical": digest(rows),
        "dataset_id": dataset_id, "version": VERSION,
        "collection_warnings": collection.get("warnings", []), "limitations": LIMITATIONS,
        "runs": [{
            "window_seconds": int(window), "status": result["status"],
            **result["counts"], "groups": len(result["clusters"]), "warnings": result["warnings"],
        } for window, result in analyses.items()],
    }
    return {
        "rows": selected, "analyses": analyses, "summary": summary,
        "provenance": {"collection": {
            **collection, "parent_post_count": len(rows), "post_count": len(selected),
            "date_filter": {"since_inclusive": start.isoformat(), "until_exclusive": end.isoformat()},
            "warnings": [*collection.get("warnings", []), *LIMITATIONS],
        }, "posts": {row["content_id"]: sources[row["content_id"]] for row in selected}},
    }


def render_report(cohorts, plan):
    """Self-contained, escaped HTML with direct source links, not bot labels."""
    def e(value):
        return escape(str(value), quote=True)

    sections = []
    for name, result in cohorts.items():
        summary, sources = result["summary"], result["provenance"]["posts"]
        handles = {a["did"]: a["handle"] for a in summary["coverage"]}
        metrics = "".join(
            f'<tr><td>{run["window_seconds"]} s</td><td>{run["eligible_events"]}</td>'
            f'<td>{run["pair_comparisons"]}</td><td>{run["baseline_trials_completed"]}</td>'
            f'<td>{run["returned_pairs"]}</td><td>{run["strong_pairs"]}</td>'
            f'<td>{run["groups"]}</td><td>{e(run["status"])}</td></tr>'
            for run in summary["runs"]
        )
        coverage = "".join(
            f'<tr><td>@{e(a["handle"])}</td><td>{a["selected_posts"]} / {a["collected_posts"]}</td>'
            f'<td>{e(a["oldest_collected_utc"])}</td><td>{e(a["stop_reason"])}</td>'
            f'<td>{"yes" if a["collected_oldest_at_or_before_start"] else "no / unknown"}</td></tr>'
            for a in summary["coverage"]
        )
        evidence = []
        for window, analysis in result["analyses"].items():
            for finding in analysis["findings"]:
                labels = [handles.get(analysis["account_labels"][key], analysis["account_labels"][key])
                          for key in (finding["source_id"], finding["target_id"])]
                posts = []
                for episode in finding["episodes"]:
                    cards = []
                    for event in episode["matched_events"]:
                        source = sources[event["content_label"]]
                        cards.append(
                            f'<article><a href="{e(source["source_post_url"])}" target="_blank" '
                            f'rel="noopener noreferrer">@{e(handles.get(event["account_label"], event["account_label"]))}'
                            f' · Open original post ↗</a><p class="muted">{e(event["timestamp"])}</p>'
                            f'<p class="post">{e(event["text"])}</p></article>'
                        )
                    posts.append(f'<p>Separation: {episode["separation_seconds"]:g} seconds</p>'
                                 f'<div class="pair">{"".join(cards)}</div>')
                evidence.append(
                    f'<details><summary>{e(window)} s · @{e(labels[0])} ↔ @{e(labels[1])} · '
                    f'{finding["episode_count"]} occasions · heuristic score {finding["score"]:.3f} · '
                    f'{"strong timing signal" if finding["strong"] else "not strong"}</summary>'
                    f'<p>Maximum shuffled count: {finding["baseline_max"]}; '
                    f'up to 12 representative occasions shown. Not a bot verdict.</p>{"".join(posts)}</details>'
                )
        previews = "".join(
            f'<li><a href="{e(sources[row["content_id"]]["source_post_url"])}" target="_blank" '
            f'rel="noopener noreferrer">@{e(handles.get(row["account_id"], row["account_id"]))}'
            f' · {e(row["timestamp"])} ↗</a><p class="post">{e(row["text"])}</p></li>'
            for row in result["rows"][:6]
        )
        warnings = sorted({warning for run in summary["runs"] for warning in run["warnings"]})
        sections.append(
            f'<section><p class="kicker">REAL PUBLIC POSTS · FIXED INPUT</p><h2>{e(name)}</h2>'
            f'<p>{e(summary["rationale"])}</p><p><strong>{summary["selected_posts"]} retained posts</strong> '
            f'from {summary["accounts_with_selected_posts"]} active accounts; '
            f'{summary["collected_posts"]} collected before date filtering.</p>'
            f'<p><a href="{e(name)}/rows.json">Download posts for the swarm UI</a> · '
            f'<a href="{e(name)}/provenance.json">Original records and source links</a> · '
            f'<a href="{e(name)}/summary.json">Full run metadata</a></p>'
            '<div class="scroll"><table><thead><tr><th>Window</th><th>Usable events</th>'
            '<th>Candidate evaluations*</th><th>Shuffles</th><th>Reported pairs</th>'
            f'<th>Strong pairs</th><th>Groups</th><th>Status</th></tr></thead><tbody>{metrics}</tbody></table></div>'
            f'<p class="muted">*Includes same-account candidates and shuffled trials, not matching posts. '
            'Baseline trials are skipped if there are no observed matches. All runs use the exact same rows; '
            '3 minimum episodes, 8 requested shuffles, 500,000 evaluation budget.</p>'
            f'<ul>{"".join(f"<li>{e(w)}</li>" for w in warnings)}</ul>'
            f'<h3>Coverage — shared filter does not mean complete coverage</h3><div class="scroll"><table>'
            '<thead><tr><th>Account</th><th>Retained / collected</th><th>Oldest collected (UTC)</th>'
            f'<th>Stop reason</th><th>Reached start?</th></tr></thead><tbody>{coverage}</tbody></table></div>'
            '<p class="muted">Reached start only means an older record was collected, not that every post '
            'or reply was captured. Zero retained posts means none were in this capped snapshot and interval.</p>'
            f'<h3>Repeated-match evidence</h3>{"".join(evidence) or "<p>No pair reached three separate matching occasions in these runs.</p>"}'
            f'<details><summary>Verify original posts — first six by time</summary><ol>{previews}</ol></details>'
            '</section>'
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width, initial-scale=1"><title>Real Bluesky cohort experiment</title>'
        '<style>:root{color-scheme:dark}body{margin:0;background:#111412;color:#f2f0e9;'
        'font:16px/1.6 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:32px 20px}'
        'h1,h2,h3{line-height:1.2}h1{font-size:clamp(2rem,5vw,3.8rem);max-width:850px}'
        'h2{font-size:2rem}a{color:#9ce7cb}section,.notice{border:1px solid #39483f;'
        'border-radius:16px;padding:24px;margin:24px 0;background:#1a211d}'
        '.kicker{color:#a7d6bf;letter-spacing:.15em;font-size:12px}.muted{color:#b4bdb6;'
        'font-size:14px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;'
        'font-size:14px}td,th{text-align:left;padding:12px;border-bottom:1px solid #39483f}'
        'details{padding:16px 0;border-top:1px solid #39483f}summary{cursor:pointer;'
        'font-weight:600}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));'
        'gap:16px}article{padding:16px;background:#111814;border-radius:12px}'
        '.post{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:12px 0}'
        '@media(max-width:650px){.pair{grid-template-columns:1fr}section{padding:16px}}'
        '</style><main><p class="kicker">VERITASSCOPE / EXPERIMENT NOTEBOOK</p>'
        '<h1>Real posts. Shared dates. Different timing windows.</h1>'
        f'<p>{e(plan["since"])} inclusive → {e(plan["until"])} exclusive. '
        'Original text, identity, links and timestamps are unchanged.</p>'
        '<div class="notice"><strong>This is not a bot verdict or an accuracy benchmark.</strong>'
        '<p>Accounts and settings were chosen before examining the collected posts. No synthetic posts '
        'were mixed into these snapshots. Shared announcements and news can produce legitimate overlap.</p>'
        '<p>The default swarm UI uses 60 seconds. Five- and fifteen-minute runs here are exploratory '
        'sensitivity checks, not changes to production defaults.</p></div>'
        + "".join(sections) + '<section><h2>Limits and interpretation</h2><ul>'
        + "".join(f'<li>{e(item)}</li>' for item in LIMITATIONS)
        + '</ul></section></main></html>'
    )


def load_json(path, limit=30_000_000):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Snapshot file exceeds {limit} bytes")
    return json.loads(raw)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory; existing evidence is refused")
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("Output directory already exists; choose a new directory")
    try:
        plan = load_json(args.plan, limit=100_000)
        if not 1 <= len(plan["cohorts"]) <= 4 or any(
            plan.get(key) != expected
            for key, expected in (("minimum_episodes", 3), ("baseline_trials", 8), ("comparison_budget", 500000))
        ):
            raise ValueError("Use 1–4 cohorts and the unchanged detector recurrence/baseline/budget settings")
        cohorts = {}
        for cohort in plan["cohorts"]:
            name = cohort["name"]
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", name) or name in cohorts:
                raise ValueError("Cohort names must be distinct simple lowercase directory names")
            path = args.plan.parent / cohort["snapshot"]
            provenance = load_json(path / "provenance.json")
            requested = {account["requested_actor"] for account in provenance["collection"]["accounts"]}
            if requested != set(cohort["actors"]):
                raise ValueError("Collected account selection does not match the predeclared cohort")
            result = compare_snapshot(load_json(path / "rows.json"), provenance,
                                      since=plan["since"], until=plan["until"], windows=plan["windows_seconds"])
            result["summary"]["rationale"] = cohort["rationale"]
            cohorts[name] = result
        report = render_report(cohorts, plan)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.exit(1, f"Experiment failed without changing input snapshots: {exc}\n")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    save_json(args.output_dir / "plan.json", plan)
    for name, result in cohorts.items():
        directory = args.output_dir / name
        directory.mkdir()
        for key in ("rows", "provenance", "summary"):
            save_json(directory / f"{key}.json", result[key])
        for window, analysis in result["analyses"].items():
            save_json(directory / f"analysis-{window}s.json", analysis)
    (args.output_dir / "report.html").write_text(report, encoding="utf-8")
    print(json.dumps({name: result["summary"] for name, result in cohorts.items()}, indent=2))


if __name__ == "__main__":
    main()