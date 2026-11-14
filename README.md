# VeritasScope

Experimental manipulation-indicator screening for pasted text and public article URLs. FastAPI/Pydantic backend; React, TypeScript, Vite and Tailwind frontend. Implements milestones A/B of [the classifier specification](docs/content_classifier.md). Local investigations persist imported observations, analysis jobs and entity reviews in SQLite. The Spot the Swarm MVP supports agent embeddings, connectivity groups and source evidence, alongside the legacy CPU-only coordination API; production deployment, authentication and real-world detection evaluation remain unfinished.

## Run locally

Requires Python 3.11+ and Node.js 20.19+ (or 22.12+).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env
npm ci --prefix frontend
```

Labeled synthetic demos and the Architecture & Example page work without keys. For arbitrary text/URLs, set `OPENAI_API_KEY` and `TYPESAFE_API_KEY` in ignored `.env`. Never put credentials in `.env.example`. Optional model overrides are `OPENAI_MODEL` (default `gpt-6-luna`) and `TYPESAFE_MODEL` (default `jev-latest`). Restart the backend after changing credentials.

Run these in two terminals from the repository root:

```bash
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
npm run dev --prefix frontend
```

Open **http://127.0.0.1:5173**. Vite proxies `/analyze`, `/examples` and `/health` to the backend. API documentation: **http://127.0.0.1:8000/docs**. `npm run build --prefix frontend` creates `frontend/dist`; API proxying is configured for local development, not a production hosting service.

## API and offline example

`POST /analyze` accepts exactly one of `text`, `url`, or `example_id`, optional `title`, `include_details` (default true), and `mode: "text_only"`. `GET /examples` lists explicit fixtures. `GET /health` reports configuration, not credential validity.

```bash
curl http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"example_id":"town-hall","include_details":true}'
```

The synthetic town-hall example includes an emoji, repeated endorsed threats, moderate emotional pressure, and a rejected quotation. Its fixed fixture profile is:

| Feature | Score |
| --- | ---: |
| Factual manipulation | null |
| Selective presentation | null |
| Emotional manipulation | 0.774648 |
| Logical manipulation | 0.637324 |
| Authority manipulation (misleading appeal only) | 0 |
| Repetition within material | 0.50 |
| Strategic persuasion | 0.75 |

The screen returns `indicators_detected`. Scores are illustrative fixtures, not model predictions. The architecture page shows the actual article, canonical claims, occurrences, section weights, coverage and exact contributions from this same offline pipeline. `public-notice` illustrates informational writing. Arbitrary text is always live input, even if it matches a sample; missing/failed providers never activate fixture scoring.

### Analyze an image

Image analysis is available when a server-side `OPENAI_API_KEY` is configured
in local `.env`; it does not require TypeSafe. Set `IMAGE_ANALYSIS_ENABLED=false`
to disable it. The default image model is `gpt-4.1-mini`; override it using
`IMAGE_ANALYSIS_MODEL`.
Restart the backend and open **Text analysis → Add image**. Choose a file
or paste a copied image or screenshot with Ctrl+V or ⌘V. Add the original
post caption if available, then select **Analyze image**. The **Image analysis**
section in `/docs` also exposes the endpoint directly.

```bash
curl -F "image=@poster.png" -F "caption=This poster is shown in a history lesson." http://127.0.0.1:8000/api/v1/images/analyze
```

On Windows, use `curl.exe`. The caption is optional. Upload one still PNG, JPEG,
or WebP at up to 5 MiB and 16 megapixels. The endpoint re-encodes the image
without metadata and sends it and the caption to the model. The application
does not create a saved dataset or job from these uploads.

The response includes a visual description, a best-effort transcription with
readability status, techniques with evidence, and the caption's stance when
supported by a verbatim excerpt. An original poster can show a technique even
when the person posting it is quoting or criticizing it. Where more context
would change the reading, the response explains what context is missing.
When the first pass proposes a technique or an explicit caption stance, a review call
sees the pixels and full caption again. It checks proposed evidence and considers
ordinary explanations such as reporting, documentation, or a routine warning.
Unsupported techniques are omitted. Ambiguous or unreviewed evidence stays unresolved.
This extra request is skipped when there are no findings or stance to review.
Results are model interpretations of the submitted material. The API does
not look up the image's origin or verify factual claims.

## Method and boundaries

- `app/content/` owns ingestion, schemas, span validation/grouping, orchestration, aggregation and policy. `app/providers/` contains reusable Luna/Jev adapters and bounded transport/cache behavior. Creator analysis remains separate future work.
- Configuration in `config/` versions the ordered seven-feature taxonomy, five-level rubrics, extraction/scoring prompts, role coefficients and experimental thresholds. Rubrics require human review before deployment. Scores describe observed strength, not probabilities of propaganda.
- Original text and submitted/final URLs are preserved. Normalization only trims outer whitespace and standardizes line endings. Extraction returns verbatim excerpts; the application derives offsets and context from unique matches within the declared paragraphs. Every source span must match the frozen normalized text, paragraph, section and exact excerpt using Unicode code-point offsets. Invalid extraction is retried once; ambiguous or unmatched excerpts are omitted with warnings.
- Equivalent claims are counted once and assigned to the earliest occurrence's section. Speakers, stance and narratives remain separate. Section relevance normalizes across sections containing canonical claims; relevance × role normalizes within each section. True all-zero relevance uses the documented uniform fallback; missing relevance withholds statement aggregates.
- Author-attributable statement scores publish only at ≥0.80 coverage. Diagnostic estimates remain separate. Stored contributions sum to the weighted mean within `1e-8`. Rejected/neutral quotations receive no author-manipulation highlights. Yellow is local score ≥0.50; red is ≥0.75. Overlaps use the strongest severity and retain all associated findings. Unicode offsets are converted with `Array.from`, preserving emoji and paragraph formatting. Repeated highlights share one canonical contribution, rather than adding it repeatedly.
- Factual manipulation and selective presentation stay `null` without external verification. Authority scores assess misleading appeals; source/endorser fabrication remains unassessed. Repetition scope is `within_material`. Contextual findings highlight only linked validated source spans; their full material score is not falsely allocated to each passage.
- The experimental screen requires emotional, logical and strategic assessment, then flags at least two available dimensions ≥0.50 with one ≥0.75. Missing required evidence, empty extraction or independent narratives produces `inconclusive`. Multiple narratives retain diagnostic/local results but withhold the combined profile. The GUI shows available diagnostic estimates with coverage and the withholding reason; they do not affect classification. Overall `risk_score` always remains `null`.
- The weighted mean is authoritative. `top_three_diagnostic` is disabled by default; enabling it reports a comparison over the three most important eligible claims, including their IDs, without changing classification.
- URL fetching validates every redirect and resolved address; the connector uses those validated IPs directly. It blocks private/reserved/multicast/transition destinations, URL credentials and nonstandard ports, ignores environment proxies, limits redirects, reads ≤2 MB uncompressed, and uses timeouts. Servers must honor `Accept-Encoding: identity`; unreadable/login/JavaScript pages, uploads and unsupported media are rejected. Articles are limited to 40,000 Unicode characters. Article HTML is never rendered in the UI.
- Two material analyses and four provider requests run concurrently. SDK retries are disabled; the wrapper retries transient failures once within a 50-second attempt timeout. Material analysis has a 240-second deadline. The in-memory cache has 128 entries and a 15-minute TTL, keyed by content/context, configuration content and versions, and response-reported model ID. Cached raw content remains process-local and disappears on restart; no history is persisted.

The content-analysis panel adds a **Propaganda score** for each statement and the material, with a brief conclusion. `/analyze` returns these as `propaganda_score` objects (`value` in 0–1 or `null`, status, label, reason and policy version); existing classification fields remain unchanged. [Explicit-score weights](config/explicit_scores.yaml) are logical 30%, strategic 30%, emotional 20%, authority 10% and repetition 10%. Statements use only their three local dimensions. Missing features are excluded and remaining weights normalized; assessed zeroes count. Partial scores are marked, and narrative review withholds the combined material score. These are experimental indicators, not probabilities.

Statement cards default to **Suspicious**: any local feature ≥0.50 keeps a statement visible, even when its combined score is lower. Fully assessed combined scores ≥0.75 receive the **Propaganda** label. **All statements** and **Unscored / partial** reveal the rest; filtering never changes material aggregation. Scores are derived from saved assessments without additional model calls and do not change swarm post scoring.

## Provider details and verification

[OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) are implemented with `AsyncOpenAI.responses.parse(text_format=Extraction)`, `store=False`, and schema-constrained Pydantic output. [TypeSafe Score](https://docs.typesafe.ai/primitives/score) uses `AsyncTypeSafeClient.system_one` with five descriptive criteria per question; raw scores are divided by four. In SDK 0.7.5, score probabilities are integer-keyed maps (serialized here as ordered five-element arrays), and the async client closes with `aclose()`. Choice/Noul and retrieval are deferred because the enabled text-only criteria use Score and do not verify truth.

Response-reported model IDs are recorded and reused on subsequent calls, with raw scores, confidence and distributions retained. If a provider returns an alias rather than an immutable snapshot, it cannot establish reproducible snapshot pinning; set account-supported immutable model IDs in `.env` for experiments. Confidence is rubric concentration, not measured predictive accuracy.

Internal tests are intentionally ignored under `.copilot-cache/`, excluded from commits and CI, per the approved plan. Checks cover randomized normalization/contribution invariants, coverage boundaries, zero and failed relevance, duplicate/quotation attribution, Unicode spans, missing evidence, API validation, provider failures/cache/SDK contracts, bounded URL ingestion and redirect/DNS safety. Frontend highlight checks exercise overlaps, exact thresholds, paragraphs and emoji. Commands when the internal validation files are present:

```bash
.venv/bin/python -m pytest .copilot-cache -q
.venv/bin/python -m compileall -q app
.venv/bin/ruff check app
npm run check --prefix frontend
npm run build --prefix frontend
node --experimental-strip-types .copilot-cache/test_highlights.ts
```

Deterministic fixture checks found zero score change from an irrelevant zero-relevance paragraph or paraphrasing with fixed assessments. Merging the town-hall section boundary changed emotional score by **0.071506** and logical score by **0.035753**. This is material sensitivity of the specified hierarchy; sectioning and live-model robustness need evaluation against human labels. These checks do not establish paraphrase robustness of either model.

Local HTTP and browser checks cover the frontend, API proxy, demos, diagnostic display, request failures and mobile layout. Live provider checks send explicitly requested text or synthetic samples. Luna extraction and Jev scoring were exercised successfully on the supplied post. No calibrated accuracy, latency target or verified propaganda verdict is claimed.

## Spot the Swarm

The current frontend's third section, **Explore connections between agents** (`/#swarm`), supports Bluesky links, CSV/JSON import and inspectable connection evidence. **Analyze activity** uses OpenAI embeddings of authored text plus a binary mention bonus to score each agent pair from 0 to 2. Teal lines scale with the score above the selected threshold; connected paths form groups. Set `OPENAI_API_KEY`. Reposts and likes do not contribute to embeddings. See [agent connectivity](docs/agent-connectivity.md) for formulas, limits, caching and API details. The legacy CPU-only temporal API remains available. Neither method establishes bot identity or measured real-world accuracy.

To analyze real activity in the same UI, expand **Import real posts from Bluesky**, paste public profile URLs, handles or exact post URLs and select **Analyze activity** once. The single action fetches the sources and automatically analyzes the saved dataset; there is no separate fetch button or profile-cap selector. Profiles fetch at most 50 recent authored posts using the API default; each post URL imports only that exact post, not the author's feed or amplification network. You can mix both, with duplicate inputs/posts removed. More than ten unique sources shows an error before collection starts. Readable account handles, original-post links and collection limits remain available with the results. A single agent cannot form a connection group. Collection uses public APIs without AI keys; the subsequent connectivity analysis requires OpenAI; it is not topic search, account discovery or repost-chain collection. Original records and source provenance persist with the dataset. See [the Bluesky collection guide](docs/real-data.md).

Use http://127.0.0.1:5173/#swarm during development. Build with `npm run build --prefix frontend` to serve the latest UI from http://127.0.0.1:8000/#swarm. Restart the backend after backend edits unless using reload. See [the swarm runbook](docs/swarm.md) for input fields, API flow, method, limitations and regression checks.

### Earlier investigation workspace

The earlier **Investigations** screen was replaced by the merged single-page frontend. Its dataset and review APIs remain available, and existing records are preserved in ignored `.local-data/investigations.db` (`DATABASE_PATH` overrides the path). Dataset-scoped IDs, analysis jobs and reviews survive restarts.
