> PARTIALLY OUTDATED: product vision retained; APIs, repository layout, execution sequence, verification scope, and evaluation details are superseded. See [implementation plan](implementation_plan.md).

# Project Outline — Explainable Propaganda & Coordinated Manipulation Detection

**Project concept:** A graph-based investigation platform that analyses both *what content says* and *how accounts spread it*. Three development tracks—**Name the Technique**, **Spot the Swarm**, and **Explainable UI**—share one data model and independently callable APIs. Designed for a live, demonstrable hackathon MVP.

## 1. Objective and scope

A user can submit a text, article, or dataset of social-media posts and interactions. The platform:

1. Identifies specific manipulation techniques, evidence spans, statement-level feature scores, and a cautiously worded content-level assessment.
2. Finds evidence of suspicious coordinated activity across accounts and content (similar posts, near-simultaneous actions, repeated URL sharing, recurring groups).
3. Presents findings in an interactive account–content graph, supports inspection of evidence and score contributions, and allows human reviewers to flag false positives.

**Two distinct inferences:** (a) manipulation in content; (b) behavioral coordination in a network. Neither alone proves that a post is propaganda, an account is a bot, or a campaign is malicious. Treat these as investigation signals, not definitive verdicts.

### MVP in scope
- Paste text and analyze it; upload or load a seeded CSV/JSON dataset with actors, posts, and interactions.
- Highlight technique-bearing spans with brief evidence-grounded explanations.
- Score the seven previously agreed manipulation dimensions on 0–1 scales at statement and content levels, with `null` for unassessable dimensions.
- Detect and visualize suspicious coordination clusters with per-cluster evidence and risk score.
- Interactive graph with account/content selection, content inspector, explanation panel, and false-positive feedback.
- Deploy a working demo (e.g., Hostinger) using Docker.

### Explicitly out of scope for the first demo
- Claiming to determine whether all claims are true from text alone.
- Claiming to prove human/bot identity or deliberate malicious intent.
- A production-grade social-media crawler, live platform integration, supervised swarm labels, or an automatic retraining loop.
- An opaque single 'propaganda percentage' treated as a calibrated probability.

## 2. End-to-end architecture

```text
                TEXT / ARTICLE / CSV / JSON INPUT
                               |
                         Ingestion / IDs
                               |
                 Shared normalized graph/events
                 /                           \
      CONTENT ANALYSIS                      SWARM ANALYSIS
      Name the Technique                    Spot the Swarm
      article -> sections -> statements     accounts / posts / actions
      technique spans + 7D features         similarity + timing + co-links
      relevance / attribution / aggregation clusters + evidence
                 \                           /
                  \     Stable JSON APIs    /
                   \                       /
                      EXPLAINABLE UI
             Graph + inspectors + evidence + feedback
```

The **backend owns ingestion and persistent canonical IDs**. Each module produces analysis *attached to those IDs*, without mutating the source observations. The frontend consumes both modules' outputs; one module is never required to finish for the other to run.

## 3. Shared domain model (freeze before parallel work)

### Nodes
| Node | Required fields | Meaning |
|---|---|---|
| `Account` | `id`, `platform`, `handle?` | An observable account or actor, **not a verified bot** |
| `Content` | `id`, `type`, `text`, `url?`, `created_at?`, `author_account_id?` | Post, article, comment, etc. |
| `Statement` | `id`, `content_id`, `text`, `start`, `end`, `role`, `attribution`, `stance` | Source-aligned atomic or coherent assertion |
| `ExternalLink` | `id`, `url` | URL/domain that content references |
| `Cluster` | `id`, `account_ids`, `content_ids` | Derived analytic grouping, not ground truth |

### Edges / events
| Edge/event | Source -> target | Fields |
|---|---|---|
| `CREATED` | Account -> Content | timestamp |
| `REPOSTED` / `REPLIED_TO` / `LIKED` | Account -> Content | timestamp, platform |
| `REPLY_TO` / `LINKS_TO` / `SIMILAR_TO` | Content -> Content or ExternalLink | optional weight/evidence |
| `CONTAINS` | Content -> Statement | char offsets |
| `COORDINATION_SIGNAL` | Account -> Account | inferred score, signal IDs, evidence — **never a declared fact** |

Use UTC ISO 8601 timestamps, stable string IDs, an explicit `analysis_version`, and immutable raw input events. Capture reposts as interactions even when the repost itself is also represented as a `Content` node.

### Canonical minimal import row
```csv
account_id,timestamp,action,content_id,text,url,reply_to_content_id
acc_01,2026-11-14T08:01:00Z,created,post_001,"Urgent: they are hiding the truth!",https://example.org/a,
acc_02,2026-11-14T08:01:24Z,reposted,post_001,,https://example.org/a,
```

**Data-engineering rule:** Observed event, model inference, and reviewer feedback must be separately represented. Keep provenance and avoid asserting author identity when the source does not provide it.

## 4. Workstream A — Name the Technique

### Goal
Understand *what the content is doing rhetorically*, identify localized evidence, and produce a decomposable content-level assessment.

### Pipeline
1. **Preprocess:** ingest text/article, keep original full text and source offsets.
2. **Structure:** article -> sections -> contextualized statements. A lightweight LLM (previous design: *Luna*) identifies main idea, statement boundaries, roles, attribution, stance, and context. Deduplicate repeated claims without losing offsets.
3. **Techniques:** classify text spans against a manageable technique taxonomy (e.g., loaded language, appeal to fear, name-calling, false dilemma, appeal to authority, repetition). Attach `start`, `end`, label, confidence, evidence, short justification. SemEval-2020 Task 11 propaganda-technique data is a potential span-label benchmark (map its labels into the chosen taxonomy).
4. **Seven-dimensional scoring:** a stronger judge (previous design: *Jev*) evaluates statement-level feature scores `x_i ∈ [0,1]^7` and statement relevance `r_i ∈ [0,1]`. Dimensions:
   - `factual_manipulation`
   - `selective_presentation`
   - `emotional_manipulation`
   - `logical_manipulation`
   - `authority_manipulation`
   - `repetition_amplification`
   - `strategic_persuasion`
5. **Relevance-weighted aggregation:** define role coefficient `q_i` (initial configurable examples: conclusion 1.0, support 0.8, counterargument 0.7, background 0.3). Compute:

   `w_i = r_i * q_i / Σ_j(r_j * q_j)`

   `F_k = Σ_i w_i * x_{i,k}` for dimensions with valid evidence/scores. Handle `null` dimensions with per-dimension normalized eligible weights rather than silently replacing missing values with zero. Capture each explainable contribution `C_{i,k} = w_i * x_{i,k}` when all relevant scores are observed; otherwise show the eligible-normalized equivalent.

6. **Interpretation:** apply an explicitly versioned rule/weight set to `F` for a content-level *manipulation signal*. Do not interpret raw scores as probabilities. Separate `no_clear_signal`, `persuasive_or_biased`, `manipulation_detected`, and `insufficient_evidence`; thresholds are configurable heuristics pending calibration.
7. **Explain:** list top contributing statements and techniques, exact source spans, feature contributions, role/attribution, what is unknown, and any context that may overturn the initial interpretation.

### Important safeguards
- **Text-only evidence cannot establish factual falsehood**: use `null` or `unverified` absent external verification. Emotional language alone is not sufficient for a propaganda verdict.
- Source attribution matters: **quoted advocacy, criticism, reported speech, and satire** must not be treated automatically as author endorsement. Preserve both rhetorical presence and author stance.
- A technique classifier's confidence is not the same thing as the 0–1 rhetorical severity feature score.
- Swarm-level repetition/coordination must not be inferred from a single article. Where unavailable, return `null` for external amplification signals.

### Outputs
- `ContentAnalysis`: `content_id`, `main_idea`, `statements`, `technique_spans`, `features`, `material_score?`, `label`, `uncertainty`, `analysis_version`.
- For every statement: offsets, attribution, stance, role, relevance, salience weight, 7D feature vector, explanation.
- For every criterion: evidence, score, top contributing statement IDs and caveats.

### Acceptance checks
- Highlight spans align to raw source text.
- At least one long article is segmented, attributed, and scored end-to-end.
- Explainability arithmetic matches returned score breakdown.
- Quoted manipulative language in a neutral report is not automatically attributed to the reporter.

## 5. Workstream B — Spot the Swarm

### Goal
Detect **suspiciously coordinated behavior** from the ways accounts interact with posts, topics, and external links—without diagnosing bot identity.

### Pipeline
1. Normalize timestamps, posts, reposts, and external URLs from shared input.
2. Build an account–content–URL graph.
3. Extract behavioral indicators, such as:
   - near-simultaneous sharing of highly similar text;
   - repeated co-sharing of the same URLs;
   - synchronized reposting bursts;
   - recurrent account overlap across distinct events;
   - unusual concentration relative to the dataset's organic baseline.
4. Calculate candidate pairwise account coordination edges using interpretable feature contributions. Use semantic similarity (e.g., sentence embeddings), lexical similarity, and temporal proximity. Previous brainstorming example: similarity >0.85 within 60s on at least 3 occasions—**initial demo heuristic only**, not a validated standard.
5. Cluster the candidate coordination graph using connected components/community detection with constraints to avoid single weak links merging unrelated groups.
6. Return a risk score `0–1` for each cluster plus **evidence items**; do not call it a probability or proof of a botnet.

### Outputs
- `SwarmAnalysis`: `clusters`, `coordination_edges`, `analysis_version`, `limitations`.
- Per cluster: `cluster_id`, participating account/content IDs, risk score, signal breakdown, representative matching posts/URLs/timestamp pairs, explanation, and uncertainty.

### Acceptance checks
- Demonstrates detection on a seeded coordinated cluster.
- Organic conversation/popular-link sharing can remain unflagged.
- Every suspicious edge/cluster can be traced to specific timed observations.
- Coordination claims are qualified as suspicious patterns, not bot attribution.

## 6. Workstream C — Explainable UI

### Goal
Make decisions auditable, understandable, and contestable rather than merely attractive.

### Main screen layout
- **Top:** dataset selector / paste-text input / upload; concise counts (content analyzed, techniques found, flagged clusters).
- **Center:** interactive graph (Cytoscape.js or equivalent): account nodes, content nodes, edges for observable actions; optional derived coordination edges in a distinct style.
- **Right inspector:** selecting content shows original text with highlighted spans, per-statement feature scores, content-level rollup, top contributing evidence; selecting an account shows its actions; selecting a cluster shows coordination evidence and timing.
- **Analysis flow panel:** show `input -> statements -> technique evidence -> feature scores -> aggregation -> interpretation` or `events -> signals -> edges -> cluster`, with clickable evidence, **not fabricated hidden model reasoning**.
- **Review control:** `Confirm`, `Dismiss / false positive`, `Needs review`, with an optional explanation and issue category. Display current review status; store feedback separately from model output.

### Recommended views
1. **Overview / Graph** — explore interactions and detected suspicious clusters.
2. **Content inspector** — highlighted techniques, main idea, individual statements, seven [0,1] bars, weights/contributions, uncertainty.
3. **Swarm inspector** — timeline of coordinated events, pairwise signal explanation, member accounts, links/posts.
4. **Review history** — human decisions and reasons; do not silently rewrite scores.

### Visual design principles
- Distinguish **observed relationships** from **inferred** connections by line styling or a visible legend.
- Show tooltips describing the *meaning* of each score, plus missing/uncertain data.
- Avoid a single red/green verdict for all types of risk.
- Allow users to click from an overview claim down to the exact highlighted evidence.
- Label synthetic demo content prominently as *simulated*.

### Acceptance checks
- Works with frozen example JSON without a live model.
- Every chart/graph click resolves to a canonical ID and opens the correct evidence.
- Both engines' results are available in one investigation.
- Feedback can be submitted, confirmed, and reflected in UI status.

## 7. API contracts: define once, then parallelize

Use FastAPI + Pydantic as a practical default; export OpenAPI schemas and generate matching frontend TypeScript types.

| API | Owner | Input | Response |
|---|---|---|---|
| `POST /api/v1/datasets` | integration/core | text or imported event set | dataset ID and normalized entity IDs |
| `GET /api/v1/datasets/{id}/graph` | integration/core | dataset ID | nodes, edges, summary |
| `POST /api/v1/content/analyze` | Name the Technique | `content_id` or text | `ContentAnalysis` |
| `GET /api/v1/content/{id}/analysis` | Name the Technique | ID | latest analysis |
| `POST /api/v1/swarm/analyze` | Spot the Swarm | dataset ID | `SwarmAnalysis` |
| `GET /api/v1/swarm/{dataset_id}/analysis` | Spot the Swarm | ID | latest analysis |
| `POST /api/v1/feedback` | UI + integration/core | target ID/type, review decision, reason | feedback record |

Use asynchronous job IDs (`202 Accepted` + polling) only if a processing task cannot reliably finish within the request timeout; for a small hackathon demo synchronous analysis is simpler.

### Shared response conventions
```json
{
  "analysis_version": "mvp-1",
  "dataset_id": "demo_01",
  "content_id": "post_001",
  "status": "complete",
  "label": "manipulation_detected",
  "feature_scores": {
    "factual_manipulation": null,
    "selective_presentation": 0.4,
    "emotional_manipulation": 0.9,
    "logical_manipulation": 0.6,
    "authority_manipulation": 0.2,
    "repetition_amplification": null,
    "strategic_persuasion": 0.7
  },
  "statements": [
    {
      "id": "stmt_001",
      "start": 0,
      "end": 41,
      "role": "conclusion",
      "attribution": "author",
      "stance": "endorsed",
      "relevance": 0.95,
      "salience_weight": 1.0,
      "feature_scores": {"emotional_manipulation": 0.9},
      "techniques": [
        {"name": "loaded_language", "start": 8, "end": 22,
         "confidence": 0.8, "reason": "Emotionally charged phrasing"}
      ]
    }
  ],
  "explanation": {
    "top_statement_ids": ["stmt_001"],
    "caveats": ["No independent factual verification performed"]
  }
}
```
*Schema above is an **illustrative partial payload**, not a complete JSON schema. Full response types should specify nullable features, provenance, review state, spans, and separate confidence/score semantics. Sample numbers are mock values.*

## 8. Repository and branch coordination

```text
project/
├── frontend/                     # UI owner
│   └── src/{components,pages,api,types}/
├── backend/
│   └── app/
│       ├── main.py
│       ├── core/                 # canonical ingestion, IDs, graph, feedback
│       ├── schemas/              # SHARED Pydantic contracts
│       ├── api/                  # routes and adapters
│       ├── techniques/           # Name the Technique owner
│       └── swarm/                # Spot the Swarm owner
├── data/demo/                    # seeded demo CSV/JSON, organic + synthetic clusters
├── tests/{contracts,techniques,swarm,integration}/
├── docs/{api,architecture}/
├── docker-compose.yml
└── README.md
```

Suggested Git branches:
- `main` — protected integrated demo.
- `feature/name-the-technique` — text pipeline and content API.
- `feature/spot-the-swarm` — graph features and swarm API.
- `feature/explainable-ui` — UI implementation against typed mocks.
- Short-lived `chore/contracts` or a small kickoff PR, merged **before** feature work diverges.

**Merge protocol:** agree on IDs, node/edge types, request/response schemas and example fixtures; merge the contracts PR; each owner works only in their module; run unit and contract tests; merge small PRs into `main` continuously instead of three late giant merges. Resolve shared `main.py` and configuration edits through a designated integrator.

## 9. Parallel execution plan for a 48-hour hackathon

### Phase 0 — Kickoff and interfaces (first ~2–3 hours)
- Define problem statement, demo narrative, taxonomy, scoring interpretation.
- Freeze canonical graph schema, endpoints, example result JSON, and IDs.
- Build a tiny shared demo dataset with one coordinated cluster, one organic group, one manipulative post, and one quoted/satirical false-positive case.
- Establish starter backend/frontend, mock routes, and baseline deployment.

### Phase 1 — Independent development
**Name the Technique:** preprocess + spans + seven-feature statement scoring + aggregation + explainable JSON; implement graceful LLM/provider fallback and mock outputs.

**Spot the Swarm:** event normalization, similarity/timing/link signals, explainable edges, cluster detection, representative evidence.

**UI:** graph explorer, inspectors, statement highlights, charts, input/upload flow, and review controls—entirely against shared mocked JSON.

### Phase 2 — Continuous integration
- Replace mocks with APIs one endpoint at a time.
- Run shared fixtures and end-to-end checks; fix ID/offset/timezone/nullable-score mismatches.
- Validate that both models can evaluate the same content nodes independently and results link to the same graph.
- Optimize responsiveness and API-cost control using caching or precomputed demo analysis.

### Phase 3 — Deployment, testing, demo
- Dockerize services; configure environment secrets on hosting, not in the frontend or repo.
- Verify dataset import, content detail, swarm evidence, human review, and page reload.
- Rehearse: suspicious article -> highlighted statements/scores -> originating/shared posts -> suspicious synchronized cluster -> human reviews a false positive.
- Document known failure modes and what is genuinely detected vs illustrative.

## 10. Demo narrative

1. Load a **clearly labeled synthetic** network of accounts, posts, and link sharing.
2. Select a post with loaded language / fear appeal; inspect exact span-level evidence and seven-dimension statement feature breakdown.
3. Show the rollup from statement salience to content-level manipulation signal.
4. Switch to the network: several accounts sharing near-identical posts in synchronized bursts are clustered. Highlight the actual posts/timestamps/links responsible.
5. Show an organic cluster or legitimate quotation that the model may initially flag. Mark it `Dismiss / false positive`, explain why, and show audit status update.
6. Conclude: the platform supports **traceable investigation**; it does not automatically prove intent or bot identity.

## 11. Quality gates and evaluation

| Workstream | MVP verification |
|---|---|
| Techniques | offset validity, span-label examples, scoring/aggregation arithmetic, quote-attribution test; optional span F1 on a small annotated sample |
| Swarm | curated positive and negative coordination cases; inspect false positives from organic reactions; score evidence completeness |
| UI | evidence click-through, distinct score meaning, keyboard/readability checks, feedback persistence |
| Integration | schema validation, stable IDs, UTC timestamps, null handling, API smoke tests, full demo flow |

Avoid reporting statistical performance from an unlabeled synthetic-only demo. If thresholds are hand-tuned, display that limitation.

## 12. Definition of done

**A live deployed UI lets a reviewer inspect a piece of content, locate the exact language responsible for a manipulation finding, see the per-statement scores and contributions, navigate to the accounts and interactions sharing related content, inspect the evidence for a suspicious coordination cluster, and correct or dismiss an interpretation—all using one coherent graph and stable IDs.**
