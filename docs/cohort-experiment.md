# Second real-data experiment: two cohorts and fixed timing windows

This follows the [first real Bluesky collection](real-data.md). Accounts and settings were recorded before collecting their feeds or inspecting detection outcomes. No original text, identity, URL or timestamp was changed. No synthetic posts were mixed into these snapshots.

## Selection and coverage

Collected on November 14, 2026 using the existing bounded public-author-feed collector:

| Cohort | Selected accounts | Collected posts | Posts retained by date filter | Usable events |
| --- | ---: | ---: | ---: | ---: |
| News organizations | 8 | 1,597 | 1,337 | 1,337 |
| Bluesky / AT Protocol ecosystem | 7 | 1,050 | 75 | 69 |
| **Total** | **15** | **2,647** | **1,412** | **1,406** |

- News: `theguardian.com`, `apnews.com`, `reuters.com`, `npr.org`, `nytimes.com`, `washingtonpost.com`, `bloomberg.com`, `politico.com`.
- Ecosystem: `atproto.com`, `bsky.app`, `pfrazee.com`, `jay.bsky.team`, `bnewbold.net`, `hailey.at`, `danabra.mov`.
- Proposed BBC, FT and some community handles did not resolve; they were excluded before feed collection. Resolving a handle is not proof of an account's safety or authenticity.
- One date filter was applied to both cohorts: **2026-11-07 00:00 UTC inclusive to 2026-11-14 00:00 UTC exclusive**. All collected posts inside it were retained regardless of detector outcome.
- Collection used 57 successful API requests, with no credentials, scraping, retries or search-endpoint bypass. Initial public-profile selection probes and the later live verification are additional requests.
- Caps remained 200 authored posts and three feed pages per account. Seven of the eight news accounts did not reach the date filter's start. The common filter therefore does **not** establish complete, balanced seven-day coverage.
- Six ecosystem accounts had retained posts; no post from `jay.bsky.team` fell inside the interval in this capped snapshot. This is not a claim about all of that account's platform activity.
- Six short ecosystem posts were excluded from detection for insufficient text and no valid URL. Derived URL links are also excluded from timing, as designed.

## Fixed-input sensitivity results

For each cohort, the **same unmodified retained rows** were analyzed at 60, 300 and 900 seconds. Minimum recurrence stayed at three episodes, with eight requested shuffled trials and a 500,000 evaluation budget. Production UI/API defaults remain unchanged at 60 seconds.

| Cohort | Timing window | Indexed candidate evaluations | Cross-account candidates | Qualifying cross-account matches | Strong pairs / groups |
| --- | ---: | ---: | ---: | ---: | ---: |
| News | 60 s | 418 | 382 | 0 | 0 / 0 |
| News | 300 s | 1,292 | 1,109 | 0 | 0 / 0 |
| News | 900 s | 3,707 | 2,988 | 0 | 0 / 0 |
| Ecosystem | 60 s | 1 | 0 | 0 | 0 / 0 |
| Ecosystem | 300 s | 9 | 5 | 0 | 0 / 0 |
| Ecosystem | 900 s | 19 | 12 | 0 | 0 / 0 |

Indexed candidate evaluations are **not matching posts**: they can include same-account comparisons. In general they also include evaluations during shuffled trials; here no observed matches qualified, so all six runs correctly skipped the shuffled trials. No budget or finding cap was exhausted.

News runs finished as `complete`; ecosystem runs were `needs_review` because of the six short posts. Neither status is a safety or bot verdict.

### A close-in-time example that did not qualify

The strongest lexical candidate in the news sample was between [a New York Times post](https://bsky.app/profile/nytimes.com/post/3mzv6k5dmjx2a) and [an Associated Press post](https://bsky.app/profile/apnews.com/post/3mzv6kmmyqf2v), about the same breaking story:

- Posting separation: approximately **15.91 seconds**.
- Token Jaccard similarity: **0.5357**, below the existing **0.85** requirement.
- No shared exact normalized URL.
- Therefore not even a single qualifying matching occasion, let alone three recurring occasions.

This demonstrates a concrete limitation of the current detector: **same topic and close timing are not equivalent to near-identical wording or shared URLs**. It does not establish whether either account is coordinated, legitimate or malicious. Across the selected news interval, none of the preserved structured URLs were shared across different accounts, even without the timing restriction.

Widening windows alone did not create qualifying matches. The appropriate next coverage improvement is genuine repost/amplification events or a preselected public topic cohort, not editing timestamps or lowering rules until a desired verdict appears. Any URL expansion or semantic matching should be a separately specified, safety-reviewed feature, not silently added to these experiments.

## Verification and viewing

- Original-record hashes and author IDs were rechecked against the live public API for **four sampled posts**, not all 2,647 posts. All four matched.
- Both retained cohorts passed real browser uploads, persisted default swarm jobs, source-text inspection and bounded graph checks with no page runtime errors.
- Offline and persisted default analyses agreed on counts, parameters, status, warnings, findings and clusters. Dataset-scoped internal IDs differ because the browser imports used different dataset names.
- The news graph showed 300 entities and reported 2,313 hidden; the smaller ecosystem graph showed all 88 entities.
- The comparison report passed desktop and 390-pixel mobile browser checks, including original-post links and downloadable row counts.

The local [comparison report](../.local-data/bluesky/cohort-experiment-20261114/results/report.html) includes account coverage, source links, settings, download links and caveats. A local-only viewer is available at [http://127.0.0.1:8765/report.html](http://127.0.0.1:8765/report.html) while its server is running.

Local evidence is intentionally ignored by Git:

- [Predeclared collection plan](../.local-data/bluesky/cohort-experiment-20261114/plan.json).
- [News posts for upload](../.local-data/bluesky/cohort-experiment-20261114/results/news/rows.json) and [ecosystem posts for upload](../.local-data/bluesky/cohort-experiment-20261114/results/atproto/rows.json).
- [Candidate audit and live-source checks](../.local-data/bluesky/cohort-experiment-20261114/results/verification.json).

These local links are not portable to another clone. Each cohort's output directory also holds original-record provenance, all three offline analyses, the persisted default analysis, a browser run summary and a screenshot. Raw collected snapshots remain separate and unchanged.

## Reproducible runner and tests

The [offline runner](../app/swarm/experiment.py) consumes a saved plan and snapshots, checks consistency against original records, applies the half-open UTC date interval, and produces all three analyses plus a source-linked HTML report. It refuses to overwrite an existing output directory. It does not collect data, call an LLM, adjust detector defaults or create provider charges.

Use the configured interpreter to run the module `app.swarm.experiment`, supplying `--plan` and a new `--output-dir`. Replaying already saved rows makes the analyses reproducible; live collection itself is not guaranteed to return the same posts later.

There are 26 new offline experiment checks for provenance tampering, unchanged source rows, date boundaries, deterministic settings, empty-sample abstention, safe report rendering, protected exports and cohort membership. They pass alongside the 26 collector checks and 22 original swarm regressions. The independent boundary suite retains its four previously documented validation failures; they are not hidden or marked as expected passes.

**No real-world precision, recall, false-positive rate or bot-detection accuracy has been established. Raw collected data and local experiment artifacts remain excluded from source control.**