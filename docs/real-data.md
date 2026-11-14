# First real-data experiment: public Bluesky author feeds

For the larger follow-up with two cohorts, a common UTC date filter, six sensitivity runs and a source-linked report, see [the second real-data experiment](cohort-experiment.md).

## What is implemented

[The opt-in collector](../app/swarm/bluesky.py) fetches public organization/account feeds from the fixed Bluesky AppView, parses real post records, and exports rows accepted by the existing import API. It does not hand-author synthetic posts, label accounts as bots, scrape webpages, follow submitted links, use private account data, or call an LLM.

Collection is now available **inside the existing Follow the pattern UI**, as well as through the original command-line collector. It is not topic search, account discovery or a continuous monitoring service. Imported rows, original-record provenance, collection jobs and analyses persist in SQLite. The standalone experiment report is optional historical evidence, not the application workflow.

Bluesky's keyword-search endpoint returned HTTP 403 in this environment. Public `getProfile` and `getAuthorFeed` requests succeeded without credentials. The collector uses those documented read endpoints, not an alternate host/proxy to bypass the denied search endpoint. Reddit was not collected in this experiment.

## Use the existing UI — no downloads or terminal required

Open **Follow the pattern** at [the main application](http://127.0.0.1:8000/#swarm), then:

1. Expand **Import real posts from Bluesky** in **Add activity**.
2. Paste one or more public profile URLs or handles, one per line. Examples: https://bsky.app/profile/bsky.app and `@atproto.com`.
3. Choose a cap of 10, 50, 100 or 200 authored posts per account and select **Fetch public posts**.
4. Review the real-post previews, readable handles, **Open original on Bluesky** links and collection-coverage disclosure.
5. Select the existing **Analyze activity** button. It reuses the saved collected dataset, preserving its original records and source links. Results, source inspection and the map stay in the same page.

Inputs accept up to ten explicit public handles, `did:plc` identities, or exact HTTPS profile URLs on `bsky.app`. Post links, article URLs, keywords, arbitrary websites, URL credentials and alternate ports are rejected. Only the fixed public API is contacted; submitted profile URLs, links and media are not fetched directly.

The collection job supports cancellation and explicit resume after a tracking error. A request already in flight can take up to 25 seconds to stop; its worker slot stays occupied until it stops. Failures preserve the previous input and completed result, and never activate synthetic fallback or automatic retries. Collection jobs share the existing two-worker limit, with at most four active/queued collection jobs. Original records are imported atomically after successful collection; cancellation or source failure before that point imports no partial snapshot.

Server-collected datasets show **REAL BLUESKY PUBLIC FEEDS**, account handles and original post URLs in results. Their coverage and collection warnings remain separate from detector warnings. Editing a collected dataset's name or raw input makes the next run user-provided input instead; the UI explicitly warns that server-collected provenance will not be claimed for that edited import.

API: `POST /api/v1/bluesky/collect` accepts `actors` and `per_actor`, returns HTTP 202 and a durable job reference. Poll/cancel through the existing jobs API. A completed collection returns `dataset_id`, `name`, importable `rows`, collection coverage and source-link metadata. `GET /api/v1/datasets/{dataset_id}/provenance` returns the saved original records and their hashes. No new database tables or AI credentials are required. Authentication, per-user rate limiting and retention controls still need deployment hardening before public exposure.

## Collect another snapshot

From the repository root, use the configured local interpreter:

```bash
.venv/bin/python -m app.swarm.bluesky --actor bsky.app --actor atproto.com --actor github.com --per-actor 100
```

Arguments:

- Repeat `--actor` for explicit public handles or DIDs (maximum 10 accounts).
- `--per-actor` is a requested cap, from 1 to 200 posts, not a guarantee of returned posts.
- At most three feed pages are fetched per account. Reposts, duplicates and invalid records can reduce the exported count.
- By default each snapshot gets a new directory under ignored `.local-data/bluesky/`.
- `--output-dir` can select a **new** directory; existing directories are refused to avoid overwriting evidence. Keep real collected data out of source control.
- Requests have timeouts and a 2 MB response cap. HTTP errors, including 403 and 429, stop the collection without automatic retries or synthetic fallback.

Each successful snapshot produces:

- `rows.json`: the original authored posts normalized for upload.
- `provenance.json`: collection times, account coverage, skip counts, source post links, original records, posting/indexing timestamps, record hashes and sampling limitations.

In **Follow the pattern**, upload the generated rows file and select **Analyze activity**. Account identifiers are stable DIDs, not mutable handles; the provenance account list maps them to the handles seen during collection.

## Verified snapshot on 2026-11-14

The first snapshot was collected at approximately 14:45 UTC with 11 public API requests:

| Selected account | Authored posts exported | Why collection stopped |
| --- | ---: | --- |
| `bsky.app` | 94 | Three-page cap; more feed data remained |
| `atproto.com` | 100 | Requested post cap |
| `github.com` | 100 | Requested post cap |
| **Total** | **294** | **Three selected organization accounts** |

The collector skipped 100 repost wrappers rather than recording them as new posts by the selected account. It deduplicated by stable post URI. Original post text was not changed or extended. Posting time comes from the record's `createdAt`; `indexedAt` is preserved separately and never used as a substitute posting time.

The selected feeds have different date coverage: the oldest collected post was 2025-12-02 and the newest was 2026-11-13. This is **not a shared, exhaustive date-range search**.

The snapshot was uploaded through the actual browser UI and analyzed by the existing CPU detector:

| Result | Verified value |
| --- | ---: |
| Job | Completed |
| Detector assessment | `needs_review` |
| Accounts with usable events | 3 |
| Authored posts imported | 294 |
| Recorded observations | 457 |
| Usable timing events | 286 |
| Short posts excluded | 8 |
| Derived post-to-URL links excluded from timing | 163 |
| Candidate event comparisons | 0 |
| Completed shuffled trials | 0 |
| Strong pairs / groups | 0 / 0 |
| Map items displayed / hidden | 300 / 145 |
| LLM/provider calls | 0 |

The job, analysis and graph persisted successfully. The browser check selected an imported post and verified that its rendered text matched the collected original. No browser runtime errors occurred. The local snapshot directory also contains the saved analysis, run summary, input hash and result screenshot generated by that check.

## What this does—and does not—demonstrate

This establishes **real API → parser → valid import → persisted detector job → rendered source evidence**. It does **not** establish bot-detection accuracy or show that these accounts are safe or unsafe.

In particular, there were no candidate comparisons inside the matching window. The engine therefore did not run shuffled trials; this is not a successful challenge against known coordination. The sample is sparse, hand-selected and missing the surrounding conversation/network.

Additional limitations:

- Only a capped sample of selected authored posts is collected. Repost wrappers and reply relationships are not reconstructed; no account-private data is requested.
- Author-provided posting timestamps are not independently verified.
- The import schema has one explicit URL field. The first valid structured URL is mapped there, while all extracted structured URLs remain in provenance. Five additional destinations in this snapshot were not mapped into that field; original text remains untouched. The detector can also read URLs literally present in the text.
- In the original file-upload experiment, coverage warnings lived in the sidecar only. The integrated collector now persists them and displays them in the existing UI's collection-coverage disclosure, separately from detector warnings.
- Source deletion/retention synchronization and continuous collection are not implemented. Review platform terms, privacy obligations and retention before deploying collection publicly.
- The previously documented CSV and extreme-timestamp API validation defects are separate and unchanged by this experiment.

A more informative next investigation would select a coherent topic or account cohort over a shared time range, retain known collection gaps, and compare results with independently reviewed labels. Do not select or alter data merely to manufacture a positive detection result.

## Checks

The collector has 26 offline checks under the repository's ignored internal-test convention. They cover identity/time/text preservation, rich-text URLs, skips, pagination, aliases, deduplication, error responses, limits and exports. They pass alongside the original 22 swarm regressions. The independent boundary suite still contains the four previously documented failures.

The integrated endpoint adds 23 offline checks for profile/URL validation, source persistence across restart, readable handles and original post links, failures without fallback, retry fingerprints, bounded queues and cooperative running cancellation. A real-network browser check fetched 15 authored posts from two selected accounts, verified the preview text against saved original records, reused the collected dataset for analysis, and inspected original-post links. It also checked invalid URL preservation, controlled cancellation and mobile layout. The existing smoke, friendly-workflow and resilience browser suites still pass. The full swarm/collector/experiment/API set has **113 passing checks and the same four known validation failures**.

Before committing, the integrated main-UI browser check was also repeated with these exact public profile URLs and a cap of 50 authored posts per account:

- https://bsky.app/profile/reuters.com
- https://bsky.app/profile/apnews.com
- https://bsky.app/profile/theguardian.com

That run fetched **150 actual posts from three accounts**, all 150 eligible for timing analysis. It verified original text/timestamp/author preservation against the saved source records, readable handles and original-post links, collected-dataset reuse, saved analysis, invalid-input preservation, controlled cancellation and mobile layout. The analysis returned six indexed candidate evaluations, no qualifying matches, no shuffled trials and zero strong pairs/groups. These are integration results, not measured bot-detection accuracy. Frontend type checking and production build also passed. Raw records and browser artifacts remain ignored local files.

### Copied-profile input regression

After a user reported HTTP 422 with those URLs, a browser reproduction found that pasting a bulleted list submitted the `-` markers as additional actors. The earlier real-network check used plain newline-separated URLs and did not cover that paste format. The same three links were valid; the input parser mishandled list formatting.

The input parser now normalizes copied list/Markdown formatting and invisible copy artifacts, validates each profile, and deduplicates selected handles. Invalid entries identify their position before any collection request is made. The existing UI layout, controls, server validation, collection limits, fixed public API destination and detector are unchanged.

Regression checks cover 14 accepted paste formats and 12 invalid/security cases on both the built app (port 8000) and Vite frontend (port 5173), plus mobile layout. These input-only checks use clearly controlled jobs, not fabricated collected posts. A separate **real-network** main-UI run pasted the formerly failing three-link bulleted list and fetched **150 actual posts from three accounts**, then verified the saved originals, post previews, source links, dataset reuse and completed analysis. Original records and test artifacts remain local and ignored.

Official API reference: [Bluesky HTTP endpoints](https://endpoints.bsky.app/). The collection and analysis checks use no API keys or AI-provider credentials.