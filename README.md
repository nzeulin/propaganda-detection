# VeritasScope

Experimental manipulation-indicator screening for pasted text and public article URLs. FastAPI/Pydantic backend; React, TypeScript, Vite and Tailwind frontend. Implements milestones A/B of [the classifier specification](docs/content_classifier.md). No deployment, authentication or persistent history.

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

## Method and boundaries

- `app/content/` owns ingestion, schemas, span validation/grouping, orchestration, aggregation and policy. `app/providers/` contains reusable Luna/Jev adapters and bounded transport/cache behavior. Creator analysis remains separate future work.
- Configuration in `config/` versions the ordered seven-feature taxonomy, five-level rubrics, extraction/scoring prompts, role coefficients and experimental thresholds. Rubrics require human review before deployment. Scores describe observed strength, not probabilities of propaganda.
- Original text and submitted/final URLs are preserved. Normalization only trims outer whitespace and standardizes line endings. Every source span must match the frozen normalized text, paragraph, section and exact excerpt using Unicode code-point offsets. Invalid extraction is retried once; unresolved spans are omitted with warnings.
- Equivalent claims are counted once and assigned to the earliest occurrence's section. Speakers, stance and narratives remain separate. Section relevance normalizes across sections containing canonical claims; relevance × role normalizes within each section. True all-zero relevance uses the documented uniform fallback; missing relevance withholds statement aggregates.
- Author-attributable statement scores publish only at ≥0.80 coverage. Diagnostic estimates remain separate. Stored contributions sum to the weighted mean within `1e-8`. Rejected/neutral quotations receive no author-manipulation highlights. Yellow is local score ≥0.50; red is ≥0.75. Overlaps use the strongest severity and retain all associated findings. Unicode offsets are converted with `Array.from`, preserving emoji and paragraph formatting. Repeated highlights share one canonical contribution, rather than adding it repeatedly.
- Factual manipulation and selective presentation stay `null` without external verification. Authority scores assess misleading appeals; source/endorser fabrication remains unassessed. Repetition scope is `within_material`. Contextual findings highlight only linked validated source spans; their full material score is not falsely allocated to each passage.
- The experimental screen requires emotional, logical and strategic assessment, then flags at least two available dimensions ≥0.50 with one ≥0.75. Missing required evidence, empty extraction or independent narratives produces `inconclusive`. Multiple narratives retain diagnostic/local results but withhold the combined profile. The GUI shows available diagnostic estimates with coverage and the withholding reason; they do not affect classification. Overall `risk_score` always remains `null`.
- The weighted mean is authoritative. `top_three_diagnostic` is disabled by default; enabling it reports a comparison over the three most important eligible claims, including their IDs, without changing classification.
- URL fetching validates every redirect and resolved address; the connector uses those validated IPs directly. It blocks private/reserved/multicast/transition destinations, URL credentials and nonstandard ports, ignores environment proxies, limits redirects, reads ≤2 MB uncompressed, and uses timeouts. Servers must honor `Accept-Encoding: identity`; unreadable/login/JavaScript pages, uploads and unsupported media are rejected. Articles are limited to 40,000 Unicode characters. Article HTML is never rendered in the UI.
- Two material analyses and four provider requests run concurrently. SDK retries are disabled; the wrapper retries transient failures once within a 50-second attempt timeout. Material analysis has a 240-second deadline. The in-memory cache has 128 entries and a 15-minute TTL, keyed by content/context, configuration content and versions, and response-reported model ID. Cached raw content remains process-local and disappears on restart; no history is persisted.

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
