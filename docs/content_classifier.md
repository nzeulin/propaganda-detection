> PARTIALLY OUTDATED: model-generated coordinates, old payload/layout examples, A/B-only scope, and implementation instructions are superseded. Preserve valid attribution and aggregation mathematics. See [implementation plan](implementation_plan.md).

# Hierarchical Propaganda-Indicator Classifier — Implementation Specification

**Status:** MVP architecture / engineering handoff  
**Version:** 0.1 (2026-11-14)  
**Objective:** Produce a comparable seven-dimensional profile of potentially propagandistic content, backed by traceable statement-level and contextual evidence. No fine-tuning is required for the MVP.

> **Important terminology:** The system detects *indicators and techniques associated with propaganda*. Emotion, persuasion, controversial opinion, disagreement, and even an incorrect factual claim are **not individually sufficient** to establish propaganda. The final binary propaganda decision is experimental until assessed against human labels. Preserve an `inconclusive` outcome.

## 1. High-level architecture

```text
Input: URL or plain-text material
         |
         v
[0] Ingest and normalize
    text, title, paragraph IDs, character offsets, metadata
         |
         v
[1] GPT-6 Luna: article structure
    main narrative(s), logical sections, atomic statements,
    roles, author stance, attributed speaker, exact source spans
         |
         v
[2] Validate and deduplicate
    validate extracted spans and attribution; cluster equivalent
    claims while preserving all original occurrences
         |
         v
[3] Jev: relevance + technique scoring
    section relevance, statement relevance, applicable
    statement-level features (rubric scores in [0,1])
         |
         +-------------------------------+
         |                               |
         v                               v
[4a] Statement aggregation        [4b] Contextual checks
     relevance/role weights            external fact verification;
     + exact attribution              omitted evidence / framing;
                                      within-article repetition;
                                      narrative-level persuasion
         |                               |
         +---------------+---------------+
                         v
[5] Material profile: seven scores + coverage + evidence
         |
         v
[6] Experimental decision policy + explainability report
```

**Models/services**
- **GPT-6 Luna** (`gpt-6-luna`): low-cost structured extraction; use OpenAI Responses API with schema-constrained JSON output.
- **Jev** (TypeSafe System One, initially `jev-latest`): rubric-based scoring through `Score`; `Choice` for checks such as support/contradiction; `Noul` for atomic yes/no detections. Pin resolved model version for reproducible experiments.
- **Optional retrieval**: fact-check/search APIs, original cited sources, and independent coverage for criteria that cannot be established from supplied text.
- **Application Python code**: claim grouping, normalized weights, feature aggregation, provenance, coverage masks, and final policy.

Documentation: https://developers.openai.com/api/docs/models/gpt-6-luna ; https://docs.typesafe.ai/introduction/quickstart ; https://docs.typesafe.ai/primitives/score

## 2. Domain entities and data contract

1. **Material:** complete content object (article, post, speech transcript), including title, original text, paragraphs and optional URL/agent/timestamp.
2. **Narrative:** central argumentative claim (or informational message if non-argumentative). Support multiple narratives, but MVP may select one primary narrative.
3. **Section:** coherent group of source paragraphs; contains statements.
4. **Statement:** *atomic contextualized proposition or argumentative unit*, not necessarily a sentence. Must retain where and by whom it was expressed.
5. **Claim group:** semantically equivalent statements/occurrences grouped into one canonical claim to prevent duplicate weighting.
6. **Agent:** author/account/site/publisher, where known; agent-level coordination is out of scope for the text-only MVP.
7. **Contextual finding:** evidence-backed fact about relationships or missing information (e.g. omission, unsupported link between claims, within-document repetition).

Canonical `Statement` fields:

```json
{
  "id": "s2",
  "canonical_claim_id": "c2",
  "text": "The tax will destroy small businesses.",
  "section_id": "sec1",
  "narrative_id": "n1",
  "source_spans": [{"start": 94, "end": 132, "paragraph_id": "p2"}],
  "context_excerpt": "...",
  "role": "supporting_claim",
  "speaker": "author",
  "stance": "endorsed",
  "is_direct_quote": false,
  "relevance": null,
  "role_coefficient": 0.8,
  "weight": null,
  "features": {},
  "score_confidence": {},
  "assessment_status": {}
}
```

- `start` inclusive, `end` exclusive, in character offsets of the **normalized full text**. Preserve the original source string and offsets; source-span validation must check correspondence.
- `role`: `main_conclusion | supporting_claim | counterargument | background | other`.
- `stance`: `endorsed | rejected | neutrally_reported | unclear` (author's stance towards the claim, **not** whether the claim is true).
- `speaker`: `author | named_source | unnamed_source | other`; store speaker name when available.
- Store quotation *content* and its attribution separately. Quoting propaganda to condemn it must not automatically count as the author's manipulation.
- For repeated claims, keep one canonical claim and an `occurrences[]` collection; do not lose citations/locations or frequency information.
- If text cannot be mapped to a source span, mark extraction as invalid and retry or omit it from scoring.

## 3. Seven-feature taxonomy

The output feature order is stable across all materials:

```python
FEATURES = [
    "factual_manipulation",       # f
    "selective_presentation",     # b
    "emotional_manipulation",     # e
    "logical_manipulation",       # l
    "authority_manipulation",     # a
    "repetition_amplification",   # r
    "strategic_persuasion",       # p
]
```

Each *assessed* feature is a score in **[0, 1]**, representing **observed strength of the specified indicator on a fixed rubric**. A score is not a probability of propaganda. Missing evidence is represented by `null`, never by zero. Report assessment status/coverage alongside the vector.

| Feature | Primary evidence | MVP decision mechanism | Caveat |
|---|---|---|---|
| Factual manipulation | claim + trustworthy externally retrieved evidence | Jev `Choice` for evidence relation, then `Score` for severity | Text-only unverifiable claims -> `null`; do not call unsupported claims false |
| Selective presentation | full narrative + comparison coverage/counterevidence | material-level Jev `Score` on concrete omissions/framing | Cannot establish omissions using only included statements |
| Emotional manipulation | statement + original passage | statement-level Jev `Score` | Emotion by itself is not manipulation |
| Logical manipulation | argument statement + premises/conclusion + nearby text | statement-level Jev `Score`; contextual finding for cross-statement errors | Conditional statements are not automatically false dilemmas |
| Authority manipulation | authority-related statement + cited reference when available | statement-level Jev `Score` on misleading appeal; verify cited sources when possible | Merely citing an expert is not manipulation; unverifiable fabrication -> `null` |
| Repetition and amplification | claim groups, repeated passages, timestamps, agent metadata | within-material repetition score from occurrence statistics and/or Jev | Cross-agent *amplification* needs network/distribution data; report scope `within_material` in MVP |
| Strategic persuasion | main narrative + document-level argument structure | material-level Jev `Score` | Ordinary opinion or advocacy must not score highly by default |

**Do not force all seven features through the statement branch.** `selective_presentation`, `repetition_amplification` and `strategic_persuasion` are primarily *material-level/contextual*. Keep links from contextual findings to associated statements/source spans for explainability.

### Rubric design

For Jev `Score`, define *five specific ordered descriptions* for each question: levels `0,1,2,3,4`. The returned score lies in `[0,4]`; normalize by dividing by `4`. Never use just the labels `none/low/medium/high/extreme` without observable definitions.

Example for `emotional_manipulation`:

```python
EMOTIONAL_RUBRIC = [
    "No manipulative emotional appeal; emotion may be present for legitimate description.",
    "Isolated, weak emotional cue that has little effect on the argument.",
    "Clear emotional appeal that reinforces an argument beyond its evidence.",
    "Strong emotional pressure central to persuading the audience.",
    "The argument relies predominantly on intense fear, anger, guilt, or comparable emotional pressure."
]
```

Implement the other six rubrics as **versioned configuration** in `config/rubrics.yaml`, with a clear level-0 and level-4 definition from the table above, and intermediate levels specified consistently. Human-review their definitions before deployment. For evidence-dependent criteria, **do not invoke** a rubric without its required inputs.

### Example Jev adapter

The following shows the *documented API shape*; production code should wrap it behind an interface and add retries, timeout, cache, model/version metadata and errors.

```python
from typesafe_sdk import Score, TypeSafeClient

question = Score(
    instructions=(
        "Rate the AUTHOR'S use of manipulative emotional appeal in target_statement, "
        "considering original_context and author_stance. Do not count quoted or "
        "rejected manipulation as the author's own technique."
    ),
    criteria=EMOTIONAL_RUBRIC,
)

with TypeSafeClient(model="jev-latest") as client:
    result = client.system_one(
        state={
            "target_statement": "If we do not stop this policy, the economy will collapse!",
            "original_context": "...",
            "main_narrative": "The proposed policy threatens economic stability.",
            "author_stance": "endorsed",
        },
        questions={"emotional_manipulation": question},
    )
    raw_answer = result.scores["emotional_manipulation"]
    normalized_score = max(0.0, min(1.0, raw_answer.score / 4.0))
    level_probabilities = raw_answer.probabilities
    decision_confidence = raw_answer.confidence
```

`confidence` indicates concentration of rubric-level probabilities, **not demonstrated predictive accuracy**. Store raw score and level probabilities; do not silently treat them as calibrated probabilities.

## 4. Processing articles and other long-form material

### 4.1 Ingestion

- Input: `text`, or `url` with optional extraction service; include `title`, `source`, `published_at`, `agent_id` where available.
- Preserve paragraph boundaries, headings, character offsets and exact quotations.
- Strip boilerplate, navigation and ads, but retain headline, subheading and substantive body.
- Do not infer publication identity/metadata from missing information.

### 4.2 Luna structured extraction

1. Extract the primary narrative as a concise *claim/conclusion*, not a broad topic label. Permit `informational` or `multiple_narratives` cases.
2. Segment article by its real headings/paragraph structure; for large inputs, use sections of approximately **200–400 words** as a starting heuristic, without splitting a quoted passage or an argument across chunks if avoidable.
3. For each section extract atomic, attributable propositions and argumentative units, with roles, speaker, stance and exact source spans.
4. Validate extracted claims against their source spans; verify the extraction has not turned an allegation or a rejected claim into an endorsed fact.
5. Merge equivalent claims across sections, keeping occurrences (and any differing stance/speaker) separately. A statement with different speakers/stance may need separate canonical nodes even if its wording is identical.
6. For very short articles, process in one extraction pass but still preserve sections/paragraph IDs.

**Suggested Luna extraction instruction:**

> Return structured JSON only. Identify the article's central argument or informational message. Split the content into minimal distinct propositions. Preserve modality, negation, uncertainty, attribution, quotation, and the author's stance; do not rewrite reports of claims into factual assertions. For each proposition, return its source character offsets and one of the allowed argumentative roles. Do not invent evidence or interpretations that cannot be supported by the input.

Require a Pydantic/JSON Schema response and retry invalid outputs. Store the model identifier and prompt/schema version. When an article contains independent central narratives, emit `narratives[]` and link each claim to its primary narrative. MVP can mark multi-narrative materials for review instead of forcing a false single narrative.

### 4.3 Deduplication and repeated claims

- Cluster near-identical proposition meaning using an optional pretrained sentence-embedding model, followed by an attribution/stance check (or use Luna for a small MVP).
- Count one canonical claim once for statement feature aggregation.
- Preserve repetition frequency, paraphrasing and positions in `occurrences[]` for criterion 6.
- Do not allow sentence-splitting choices to arbitrarily multiply a proposition's score.

## 5. Relevance and argumentative-role weights

### 5.1 Inputs scored by Jev

For section `j`: `R_j in [0,1]` = importance of section to the primary article narrative.

For canonical statement `i` in section `j`: `r_i in [0,1]` = importance of the statement to understanding the central narrative, including essential support and substantive rebuttal. **Do not ask only about semantic similarity or agreement.**

Example five-level relevance rubric: `unrelated`, `minor tangential detail`, `relevant context`, `important support/rebuttal`, `essential claim or conclusion`; replace with detailed descriptions in configuration.

### 5.2 Role coefficients (MVP hypotheses)

| Role | `q_i` |
|---|---:|
| `main_conclusion` | 1.0 |
| `supporting_claim` | 0.8 |
| `counterargument` | 0.7 |
| `background` | 0.3 |
| `other` | 0.4 |

These are *configurable heuristics*, not learned parameters. Attribution and stance are **separate from** the role coefficients. Neutral/rejected quotations must not become author-attributed manipulative evidence just because their salience is high.

### 5.3 Hierarchical normalization

For the section level:

```text
v_j = R_j / sum_m R_m
```

Within section `j`:

```text
a_i|j = (r_i * q_i) / sum_{t in section j}(r_t * q_t)
```

Global normalized statement importance:

```text
w_i = v_section(i) * a_i|section(i)
```

For a single-narrative material with at least one scorable statement, `sum_i w_i = 1`.

**Fallbacks:** If all section relevance scores are zero, use uniform section weights and log a warning. If all within-section weighted relevance values are zero, use uniform within-section weights and log a warning. If no statements were extracted, return `inconclusive` with `extraction_failed` instead of dividing by zero.

This hierarchy prevents sections with many extracted statements from automatically dominating merely through statement count.

## 6. From statements to article-level features

Let `x_i,k in [0,1]` be the score for criterion `k` on statement `i`, **only when that criterion is validly assessed for that statement**. Missing `x_i,k` is `null`.

### 6.1 Statement-derived criterion

For a criterion `k` assessed on eligible author-attributable statements `E_k`:

```text
coverage_k = sum_{i in E_k} w_i
A_k = (sum_{i in E_k} w_i * x_i,k) / coverage_k
```

`A_k` remains in `[0,1]`. If `coverage_k == 0`, set `A_k = null`. Define a configurable minimum coverage threshold (initial exploratory default **0.80**); below it, set published `A_k = null` but retain diagnostic partial estimates and coverage. This avoids giving a high-confidence score when most relevant claims were unassessed.

The exact contribution of eligible statement `i` to an assessed statement-derived feature is:

```text
C_i,k = (w_i * x_i,k) / coverage_k
A_k = sum_{i in E_k} C_i,k
```

Save `C_i,k` for explanations. Do not re-label `0.0` as missing or missing as `0.0`.

### 6.2 Context-derived criterion

For omission/framing, repetition, strategic narrative pattern, and inter-statement relationships, compute `G_k in [0,1]` from a documented rubric or deterministic procedure. Save `contextual_findings[]` with the source spans, evidence URLs, linked statement IDs and score contributions.

**MVP wiring:**

| Feature | Material-level score |
|---|---|
| `factual_manipulation` | `A_factual`, only after evidence checks |
| `selective_presentation` | `G_bias`, only with relevant comparison evidence |
| `emotional_manipulation` | `A_emotional` |
| `logical_manipulation` | `A_logical`; flag unresolved cross-statement reasoning gaps separately |
| `authority_manipulation` | `A_authority`, with required verification for claims of fake citations/endorsers |
| `repetition_amplification` | `G_repetition` for within-material repetition; scope explicitly marked |
| `strategic_persuasion` | `G_persuasion`, evaluating *manipulative* narrative pattern, not ordinary advocacy |

Later, if a criterion legitimately combines statement and contextual evidence, use a versioned convex combination:

```text
F_k = (1 - lambda_k) * A_k + lambda_k * G_k
```

with both parts assessed and `lambda_k in [0,1]`. Do not silently replace a missing part by zero or renormalize without an explicit coverage policy.

### 6.3 Final feature vector and comparability

```text
F_M = [factual, selective, emotional, logical,
       authority, repetition, persuasion]
```

Return **exactly these seven keys in fixed order**, with values `number in [0,1] | null`. Also return a seven-element availability mask, per-feature scope (`text_only`, `source_verified`, `within_material`, `cross_agent`), rubric/model versions, and evidence coverage. Compare materials only on compatible, assessed feature dimensions. Do not interpret Euclidean/cosine similarity computed on incomplete or differently defined vectors as meaningful without masking/version checks.

### 6.4 Length robustness / optional pooling experiment

The weighted mean is **the required baseline**. It can dilute one powerful central propaganda statement among many neutral claims. Implement an **optional experiment** comparing weighted mean with a salient top-`k` score or max-weighted blend; keep it disabled by default until evaluated. Preserve source attribution for whichever pooling rule is enabled.

## 7. Final classification policy

**MVP delivers the feature vector even when binary classification is inconclusive.** Do not label a material propaganda solely because it contains emotion, advocacy, or an individual wrong statement.

Two output modes:

- **`text_only`**: return available features and `classification` (`suspicious | propaganda | no_strong_text_indicators | inconclusive`). These are experimental screening labels. Historical `indicators_detected` records remain readable.
- **`evidence_enriched`**: when sufficient relevant verification is present, a separately configurable, versioned policy can return a **provisional** `propaganda_indicators_detected | no_significant_indicators | inconclusive`. The policy needs validation against human labels.

The text assessment and material score share the weights in `config/policy.yaml`: logical 30%, strategic 30%, emotional 20%, authority 15%, repetition 5%. Text excludes missing optional dimensions and normalizes remaining weights; missing required emotional/logical/strategic evidence or narrative review withholds classification. Post screening uses the same weights with missing dimensions set to zero. Statement scoring retains separate weights and 50/75 cutoffs.

```text
weighted_score = sum_k alpha_k * F_k   # alpha_k >= 0; sum_k alpha_k = 1
# < 0.35: no strong indicators; >= 0.35: suspicious/review; >= 0.50: propaganda
```

Return `classification.weighted_score = null` when classification is withheld; `risk_score` remains `null` throughout. Never present the weighted score as calibrated `P(propaganda)`. The configurable weights and thresholds are experimental policy choices requiring validation against human labels.

A more expressive downstream classifier can be trained later on the feature vectors; **that is not required for this MVP**.

## 8. Explanation / exact attribution

For every material score, include:

- Its value, `assessed/not_assessed`, evidence requirements, coverage and model/rubric version.
- For statement-derived features: the top `C_i,k` contributors, the original text and source spans, role, stance, `r_i`, `q_i`, `w_i`, and `x_i,k`.
- For contextual features: the observed pattern (e.g. omitted relevant counterevidence), linked statements and retrieved sources, and the contextual rubric score.
- For the final decision: which **material features** triggered the versioned policy; do not invent causal explanations not supported by the calculation.

Explainability guarantee: **statement-derived score = sum of stored statement contributions** (within numerical tolerance). Contextual evidence contributes through explicitly documented findings and is **not falsely attributed entirely to individual statements**.

## 9. API contract

`POST /analyze`

```json
{
  "text": "The government introduced a tax. Critics say it will destroy businesses...",
  "title": "A new tax policy",
  "mode": "text_only",
  "include_details": true
}
```

Illustrative response shape (scores below are examples only):

```json
{
  "material_id": "m_001",
  "model_versions": {"extractor": "gpt-6-luna", "scorer": "jev-latest"},
  "taxonomy_version": "v0.1",
  "primary_narrative": "The proposed tax is dangerous and should be opposed.",
  "features": {
    "factual_manipulation": null,
    "selective_presentation": null,
    "emotional_manipulation": 0.70,
    "logical_manipulation": 0.76,
    "authority_manipulation": null,
    "repetition_amplification": 0.10,
    "strategic_persuasion": 0.80
  },
  "availability": {
    "factual_manipulation": false,
    "selective_presentation": false,
    "emotional_manipulation": true,
    "logical_manipulation": true,
    "authority_manipulation": false,
    "repetition_amplification": true,
    "strategic_persuasion": true
  },
  "coverage": {
    "emotional_manipulation": 1.0,
    "logical_manipulation": 1.0
  },
  "classification": {
    "mode": "text_only",
    "label": "propaganda",
    "weighted_score": 0.60,
    "risk_score": null,
    "policy_version": "experimental-weighted-v1"
  },
  "sections": [],
  "statements": [
    {
      "id": "s3",
      "text": "If we don't stop the policy, the economy will collapse!",
      "role": "main_conclusion",
      "stance": "endorsed",
      "relevance": 0.95,
      "role_coefficient": 1.0,
      "weight": 0.52,
      "features": {"emotional_manipulation": 0.94},
      "contributions": {"emotional_manipulation": 0.4888},
      "source_spans": [{"start": 100, "end": 153, "paragraph_id": "p3"}]
    }
  ],
  "contextual_findings": [],
  "warnings": ["Factual claims not externally verified"]
}
```

**Note:** The example is a *schema illustration*, not a mathematically complete scored article. In a real response, output the other statements and contributions so they sum to reported statement-derived material scores; example offsets must always be verified against actual input text.

## 10. Suggested Python project structure

```text
propaganda-classifier/
  README.md
  pyproject.toml
  .env.example                    # OPENAI_API_KEY, TYPESAFE_API_KEY
  config/
    taxonomy.yaml                # ordered seven features, required evidence
    rubrics.yaml                 # versioned Jev question descriptions
    roles.yaml                   # q_i coefficients
    policy.yaml                  # modes, coverage thresholds, decision policy
  app/
    main.py                      # FastAPI: POST /analyze, GET /health
    schemas.py                   # Pydantic request/response/entities
    ingestion.py                 # text normalization + source span mapping
    extraction.py                # Luna structured output and sectioning
    verification.py              # offset/stance validation, deduplication
    jev_client.py                # isolated Jev Score/Choice/Noul adapter
    relevance.py                 # section and statement relevance
    scoring.py                   # statement/contextual criteria
    evidence.py                  # optional retrieval + source verification
    aggregation.py               # deterministic hierarchical math
    policy.py                    # experimental final decisions
    explanations.py              # exact contributions + provenance
  tests/
    test_extraction.py
    test_aggregation.py
    test_attribution.py
    test_missingness.py
    test_quote_stance.py
    test_robustness.py
    fixtures/                    # synthetic and annotated samples
```

Use `openai`, `typesafe-sdk`, `pydantic`, `fastapi`, and `pytest`. Add retrieval/embedding dependencies only when the corresponding optional module is enabled. Introduce dependency injection and mock implementations so tests do **not** require real API keys or calls.

## 11. Implementation sequence

### Milestone A — deterministic skeleton (must work offline)
1. Create Pydantic models, API endpoint and mock extractor / mock Jev client.
2. Implement normalized section/statement weights and missing-value-safe aggregation.
3. Implement exact statement contributions and score coverage.
4. Add tests for all mathematical invariants.

### Milestone B — live text-only prototype
5. Integrate `gpt-6-luna` with strict structured output for main idea, sections, atomic statements, role/stance/source spans.
6. Validate spans; group duplicates while preserving occurrence counts.
7. Integrate Jev relevance and text-assessable rubrics; cache results by `(text, context, question_version, model_version)`.
8. Add within-material repetition and narrative-level strategic persuasion scoring.
9. Return a seven-key vector with unavailable criteria as `null`, explanations and text-only indicator label.

### Milestone C — source-enriched evaluation
10. Retrieve sources for central factual claims; explicitly score supported/contradicted/insufficient evidence and authority-reference validity.
11. Retrieve relevant counterevidence for selective presentation; document what was compared.
12. Add an annotated benchmark; evaluate per-feature and final-decision precision, recall, false-positive rates, and stability.
13. Only then enable an evidence-enriched binary screening policy.

**Out of scope for MVP:** agent network detection, reliable inference of author intent, fully automatic proof of deliberate deception, fine-tuning, and calibration claims unsupported by a benchmark.

## 12. Acceptance criteria and tests

- [ ] Given a short article, extract a central narrative and contextualized statements with source spans and argument roles.
- [ ] Preserve the distinction between authored claims, quoted claims, rebuttals, and neutral reporting.
- [ ] Score relevant statements with Jev through a reusable adapter; normalize `Score/4` to `[0,1]`.
- [ ] Generate a fixed-order seven-feature material profile; use `null` with coverage/status when unassessed.
- [ ] For nonempty, single-narrative material: each level's normalized weights and final statement weights sum to 1 (tolerance `1e-8`).
- [ ] For each statement-derived material criterion: `abs(sum(contributions) - score) < 1e-8`.
- [ ] Deduplicating a repeated claim does not multiply its effect on non-repetition criteria; its occurrence count remains available for repetition detection.
- [ ] Adding an irrelevant paragraph, paraphrasing, or shifting section boundaries is explicitly tested for score stability; any substantial variation is reported.
- [ ] A sentence quoted and *rejected* by the author is not incorrectly treated as the author's endorsement.
- [ ] Missing fact-checking sources do not produce fabricated factual or authority-verification scores.
- [ ] All labels and thresholds are versioned; the default text-only output is described as a **screening assessment**, not a validated truth judgment.
- [ ] Full pipeline runs with mocks; separate opt-in integration tests run with real API keys.

## 13. Open design decisions for later empirical evaluation

1. Does `Score` outperform a group of `Noul` questions plus deterministic category aggregation on actual propaganda-technique annotations?
2. Do the heuristic role weights improve human-rated relevance and robustness compared with relevance only (`q_i = 1`)?
3. Should highly salient manipulative passages affect feature scores through weighted mean, max, or top-k pooling?
4. How should independent narratives within one article be aggregated without suppressing minority but central arguments?
5. Which features should require source verification, and what minimum assessment coverage is adequate?
6. How should seven correlated feature dimensions contribute to the final classification without double-counting a single technique?

**Suggested benchmarks:** SemEval-2020 Task 11 and SemEval-2023 Task 3 for technique/span detection. They do not directly validate all seven continuous material-level dimensions; create a small human-annotated material-level set for that purpose.

## 14. Instructions to the implementing agent

Build the **Milestone A + Milestone B** solution first. Do not silently swap the selected providers or invent a trained classifier. Follow the seven-feature order, schemas, missingness policy, source-attribution rules, and aggregation formulas in this document. Implement mocks before live API integration; keep all rubric prompts configurable. Return working code, tests, a `.env.example`, local run instructions, and a sample analyzed article. Label all heuristics and provisional decisions explicitly. When provider API details differ from this handoff, defer to the provider's current official documentation and record the change in `README.md`.
