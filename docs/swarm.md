# Spot the Swarm: local minimum working detector

The third section of the current single-page UI (`/#swarm`), **Follow the pattern**, runs a real CPU-only coordination detector. It does not classify accounts as proven bots or infer malicious intent. Analysis needs no AI provider credentials, scraping or external requests; the optional explicit Bluesky import contacts its public API to collect selected accounts' posts.

## Try it

Start the backend and Vite using the repository's local startup instructions. During development open http://127.0.0.1:5173/#swarm. After `npm run build --prefix frontend`, the backend serves the same interface at http://127.0.0.1:8000/#swarm. Restart the backend after backend changes unless it was started with reload.

Choose a demo card or use **Start with a demo**, then select **Analyze activity** (or **Analyze loaded demo**):

- **Coordinated network:** the same 172 observations as `data/demo_network.json`; 26 accounts, two synchronized three-account groups and 20 background accounts. The default v2 detector returns two groups and six strong pairs on this deliberately easy fixture.
- **Library announcement:** four library branches share a launch URL once and post separate later updates. No strong recurring group should be returned. This is a limited contrast case, not evidence that legitimate recurring campaigns are reliably distinguished.
- **Missing timestamps:** repeated text without timing evidence must return `insufficient_data`, not a clean verdict.

The interface guides you through **Add activity → Find repeated patterns → Read the evidence**. The expandable quick guide explains accounts, posts, recorded actions, usable activity, matching occasions and groups. “Matching occasion” is the plain-language label for an episode; “group” and “cluster” mean the same thing. Data previews are readable without opening the optional raw JSON/CSV editor.

Results lead with a plain-language takeaway and explain each count. Choose a group or account pair to compare its supporting posts side by side (stacked on mobile). Expand **Why is the score…?** for the actual formula, input values, worked calculation and shuffled counts. Technical evidence, identifiers and method details remain available in expandable sections. The network map follows the evidence, with a shortcut from the result summary. These presentation changes do not change detector scores or thresholds.

Alternatively upload CSV/JSON or paste event rows. JSON is an array, not a graph. Required fields are `account_id`, `content_id`, `action` and readable `text` or an absolute HTTP(S) `url` for created content. Use ISO 8601 timestamps with `Z` or an explicit UTC offset. `platform` is optional. Reposts, replies and likes must reference content with a corresponding created observation. Imports are atomic, dataset-scoped, deduplicated and limited to 5,000 rows / 10 MB. Source input and results persist in local SQLite; only import data you are permitted to store.

To fetch real posts without exporting files, expand **Import real posts from Bluesky**, enter public profile URLs or handles, choose a per-account cap and select **Fetch public posts**. Review the readable handles, original-post links and collection coverage, then use **Analyze activity**. Everything stays in this UI. This collects selected authored feeds—not keyword search, discovered accounts or repost chains. See [the integrated Bluesky guide and earlier experiments](real-data.md) for limitations and API details.

## API flow

1. `GET /api/v1/swarm/examples`: synthetic input rows with descriptions, never precomputed verdicts.
2. `POST /api/v1/datasets`: `{name, rows}` or `{name, csv}` creates an immutable dataset.
3. `POST /api/v1/swarm/analyze`: `{dataset_id}` returns a queued job with HTTP 202.
4. `GET /api/v1/jobs/{job_id}`: poll until completed, failed, cancelled or interrupted. Queue/run status is separate from the detector's assessment status.
5. A completed job's `result` contains status, warnings, parameters, counts, account labels, pair findings and groups. Episodes include the strongest supporting event IDs, account labels, source text previews, timestamps, lexical similarity and shared URLs.
6. `GET /api/v1/datasets/{dataset_id}/graph` includes observed relationships and strong inferred links. At most 300 entities are displayed; hidden entities are counted. The detector itself uses the full imported dataset.
7. `GET /api/v1/swarm/{dataset_id}/analysis` returns the latest saved analysis. `POST /api/v1/jobs/{job_id}/cancel` cooperatively stops a queued/running job. Failed or interrupted jobs may be explicitly retried through the existing jobs API.

For real Bluesky input, use `POST /api/v1/bluesky/collect` with `actors` and `per_actor` before step 3. It returns a collection job; on completion its `dataset_id` is already persisted, so no separate manual import is needed. The saved source records are available through `GET /api/v1/datasets/{dataset_id}/provenance`. Collected analyses carry collection coverage and readable handles; graph content and matched evidence include original-post URLs.

## Method and boundaries

- Eligible events are created, reposted or replied-to observations with timezone-aware timestamps and at least four distinct text tokens or a valid URL. Likes and derived `links_to` actions are not timing evidence.
- A pair matches within 60 seconds when it shares a URL or at least four distinct tokens with lexical Jaccard similarity at least 0.85. URLs are removed from lexical tokens to avoid bypassing their specificity discount. No URLs are fetched. Query strings are preserved; fragments and default ports are normalized.
- One episode is matching pair activity, extended until there is more than 60 seconds of inactivity. A continuous stream does not accumulate fixed-window "episodes". Evidence belongs to the strongest representative match inside that episode.
- At least three episodes are required. The score combines mean signal strength with excess recurrence over the maximum of eight timestamp-shuffled baselines. Strong pairs need at least two excess episodes and score at least 0.5. Complete-link groups contain at least three mutually strong accounts.
- The sample is insufficient if fewer than two accounts have three eligible events each, or its eligible-event time span is no longer than 120 seconds. Adequate data with no findings is still not proof of safety.
- Comparisons are capped at 500,000 across observed and shuffled runs. Exhaustion, or truncation above 500 returned candidate pairs, withholds all strong assertions. At most 12 representative episodes per pair and 1,200 characters per text preview are returned, with warnings; scores use all counted episodes.
- Missing or unusable observations are counted and warned about. New malformed explicit URLs are rejected at import; malformed URLs in embedded text or legacy data are ignored with warnings rather than crashing the job.
- The shuffle preserves global activity times and account event counts, not each account's rhythms. Eight trials are diagnostic, not statistical significance or calibrated confidence. Fixed seeds and sorted processing make the same dataset reproducible.
- Legitimate scheduling, news sharing, syndication and campaigns can produce coordination signals. Paraphrases and less tightly connected groups may be missed. Precision, recall and false-positive rate have **not** been measured on a real-world benchmark.

This is a local investigation tool. Authentication, per-user abuse protection, data-retention controls, continuous collection, account discovery and deployment hardening remain separate work before public exposure. The integrated Bluesky collector is explicitly initiated and bounded, not a platform-wide crawler.

## Local regression checks

Per the existing repository convention, internal tests are ignored under `.copilot-cache/`. Run `.venv/bin/python -m pytest .copilot-cache/test_swarm.py -q` locally. The suite covers real example outcomes, source-evidence consistency, continuous bursts, abstention, malformed/common URLs, deterministic results, resource limits, cancellation, JSON/CSV imports, saved graphs and persistence across a server lifespan restart. API checks use an isolated temporary database and disable live provider keys.

An independent boundary pass adds `.copilot-cache/test_swarm_boundaries.py`. Run both suites together to include known failure reproductions. The combined result is currently **38 passing and 4 failing checks**, covering three confirmed API input-validation defects. See the [test report](swarm-test-report.md) for reproduction details, browser results and remaining limitations.