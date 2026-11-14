# Complete local investigation release

Status: specification recorded; implementation beyond the existing text pipeline pending.
This document governs the release. A checked requirement requires recorded verification.

## Scope and constraints

CPU-only laptop execution; reference benchmark: four cores, 16 GB RAM. No local language
model training, fine-tuning, or GPU requirement. Keep FastAPI, React/TypeScript, and the
existing content pipeline. Use SQLite/WAL, SQLAlchemy, and versioned migrations for local
persistence. Local Docker demonstration first; public Hostinger deployment is deferred.

Use GPT-6 Luna for extraction, Jev for rubric and evidence-relation scoring, and
`gpt-6.1-sol` for initial and deeper factual verification. Check model/tool access before
live acceptance. Never silently substitute providers. Credentials remain server-side in
ignored `.env`. Optional semantic embeddings use an API, not a local transformer.

Limits: 10 MB imports, 5,000 events per dataset, 40,000 characters per material, two
concurrent material jobs, four provider requests. Dataset import does not automatically
purchase analysis of every post. Selected live materials always receive fact-checking.

## Canonical entities and persistence

Store immutable observed datasets, accounts, content, external links, and events separately
from versioned analyses, source evidence, coordination findings, jobs, and append-only
review decisions. Imported IDs are dataset-scoped. Keep identical texts from distinct
accounts as distinct observations; analysis caching must not merge their provenance.

Validate CSV and JSON atomically with row-level errors. Preserve original URLs, text,
source IDs, and timestamps. Normalize known timestamps to UTC; unknown timestamps cannot
participate in temporal coordination. Reject conflicting duplicate IDs and oversized imports.

## Background work

Submit analysis as persistent jobs with HTTP 202 and one-second frontend polling. Record
stage status, elapsed time, completed units, artifacts, warnings, and categorized errors.
Support cancellation, explicit retry, reload recovery, and saved analysis revisions.
Mark interrupted jobs after restart; never silently repeat paid work. Deduplicate in-flight
requests and cache by input, configuration, model identity, and evidence fingerprint.
Preserve successful stage results when later stages fail.

## Content and verification

Preserve local exact-quotation anchoring, stance and speaker attribution, deduplication,
section/claim weights, coverage, and exact contributions. Add a versioned technique taxonomy
and short source-grounded explanations. Never invent hidden model reasoning. Keep provider
confidence separate from severity, completeness, and reviewer decisions.

Every live content run identifies checkable propositions and performs initial fact-checking,
even for apparently benign material. Separate opinions and unverifiable predictions. Sol
retrieves relevant primary and independent sources. Fetch evidence through existing bounded
public-URL protections; retain exact excerpts, URLs, dates, hashes, and claim references.
Jev Choice assesses supported/contradicted/mixed/insufficient evidence; Score assesses
applicable severity. Source copies are not independent corroboration. Absence of evidence
is not falsehood. Assess selective presentation only against a documented comparison corpus.

Automatically run one deeper verification pass for missing/conflicting material evidence,
attribution/date uncertainty, insufficient coverage, scores within 0.10 of a policy boundary,
evidence-relation confidence below an initial configurable 0.70, or disagreement between
preliminary assessment and evidence. Apply escalation to potential positive AND negative
outcomes. These are experimental triggers, not calibrated confidence guarantees.

Across both passes allow at most 20 searches, 40 fetched documents, and ten minutes per
material. Prioritize central claims and explicitly record any unchecked claims. Keep text
indicators separate from verification completeness. Unresolved final investigations remain
inconclusive/needs review with available scores visible. Synthetic demonstrations verify
against labeled packaged evidence; do not treat fictional entities' absence from web search
as evidence of deception.

## Coordination

Run independently of content classification. Match lexical text, optional API embeddings,
shared URLs, temporal synchronization, and recurrent pairs using indexes and time windows.
Initial configurable thresholds: 60 seconds; lexical similarity 0.85 or semantic cosine 0.90;
at least three distinct episodes. Deduplicate imported actions and within-episode matches.
Downweight ubiquitous URLs. Compare with timestamp-shuffled activity-preserving baselines.
Store signal contributions and original event IDs for each finding.

Cluster strong edges, subdivide loose components, and enforce at least three accounts and
internal density 0.5. Avoid weak-bridge merging. Report suspicious coordination, not proof
of bot identity or malicious intent. Publish exact score formula and version before release.

## Interfaces

Generate frontend contracts from OpenAPI. Preserve existing endpoints during migration.

| Endpoint | Contract |
|---|---|
| POST /api/v1/datasets | Atomic text/URL/CSV/JSON import |
| GET /api/v1/datasets | Saved investigations |
| GET /api/v1/datasets/{id}/graph | Filtered bounded graph with canonical IDs |
| POST /api/v1/content/analyze | Job for selected content plus mandatory verification |
| GET /api/v1/content/{id}/analysis | Latest or selected revision |
| POST /api/v1/swarm/analyze | Independent coordination job |
| GET /api/v1/swarm/{dataset_id}/analysis | Coordination result and evidence |
| GET /api/v1/jobs/{id} | Progress, partial results, categorized failures |
| POST /api/v1/jobs/{id}/cancel | Cancel queued/active work |
| POST /api/v1/feedback | Append revision-specific review |
| GET /api/v1/feedback | Review history |
| GET /api/v1/system | Module definitions and capabilities |
| GET /api/v1/analyses/{id}/trace | Sanitized execution artifacts |
| POST /api/v1/evaluations | Resumable evaluation job |
| GET /api/v1/evaluations/{id} | Metrics, errors, provenance, and progress |

## GUI

Maintain navy/cyan styling, readable typography, restrained warning colors, responsive layouts,
keyboard navigation, and reduced motion. Every visible control must work.

Provide investigations, imports, progress, saved reviews, JSON export, and print-friendly HTML.
Use Cytoscape.js for account/content/URL exploration: observed versus inferred edge styles,
search, time filters, cluster selection, neighborhood expansion, reset, and an initial cap of
300 visible nodes. Selection synchronizes graph, timelines, source text, and evidence by ID.

Show seven scores, null reasons, coverage, exact highlights, source comparisons, statement
contributions, coordination episodes, and confirm/dismiss/needs-review decisions.

Build a React Flow system explorer covering ingestion, extraction, anchoring, scoring,
initial/deeper verification, aggregation, coordination, and review. Clickable modules show
actual inputs, outputs, provider, timings, warnings, and artifact links. Include live stage
progress, saved-trace play/pause/step/reset, follow-a-claim and follow-a-signal navigation,
and a formula simulator whose hypothetical results never overwrite saved analyses.
Display exact decision paths for an optional shallow tree. Clearly label synthetic replay.

Add evaluation views for split/provenance, per-family metrics, confusion matrices, false
positives/negatives, abstentions, evidence coverage, escalation, latency, and API usage.
Link each error to its text, reference annotation, evidence, and prediction.

## Delivery sequence and acceptance matrix

| Milestone | Required deliverable | Exit gate | Status |
|---|---|---|---|
| 1 | Documentation and contracts | Scope, API inventory, dataset protocol, outdated labels | Documentation recorded; contracts pending |
| 2 | Persistence/imports/jobs | IDs, atomic import, restart, cancellation, feedback persistence | Pending |
| 3 | Canonical content integration | Existing regressions plus explanations and traces | Pending |
| 4 | Sol verification cascade | Positive/negative uncertainty, evidence, budget termination | Pending |
| 5 | Swarm engine | Seeded positives, organic negatives, timed evidence, weak bridges | Pending |
| 6 | Investigation GUI/system explorer | Linked browser journeys, real module artifacts | Pending |
| 7 | Dataset/evaluation | Pilot, accepted 1,500 records, web set, frozen splits, metrics | Pending |
| 8 | Demo hardening | Fresh Docker startup, offline replay, exports, failure rehearsal | Pending |

Use meaningful commits. Internal tests belong in ignored `.copilot-cache/.tests/`; no CI
changes. Complete the actual file inventory and verification records as implementation advances.

## Release gates

Validate source offsets/Unicode/quotes, missingness, zero scores, attribution, weight sums,
and contribution equality within 1e-8. Validate IDs, UTC handling, import rejection, migrations,
job recovery, evidence provenance, every escalation branch, budget exhaustion, coordination
arithmetic, and cluster boundaries. Audit dataset balance and cross-split leakage.

Browser-test import → analysis → graph → exact evidence → sources → coordination → review →
reload → export, plus system replay and evaluation error analysis. Inspect desktop/mobile
screenshots, keyboard operation, reduced motion, overflow, and console errors.

Measure on the declared laptop: job acknowledgement <1s, a 300-node graph interactive <2s,
and 5,000-event local coordination <30s. Record actual provider latency separately. Run
provider-failure rehearsals and a fresh-start demonstration. Do not claim untested capability
or blanket flawlessness. Identify tested commit, environment, datasets, results, and limits.
