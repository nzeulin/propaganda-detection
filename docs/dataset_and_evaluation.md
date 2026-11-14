# Dataset and evaluation protocol

Status: specified; datasets have not yet been generated or collected.

## Accepted synthetic corpus

Exactly 1,500 accepted materials: 450 clear negatives and 150 for each dominant family:
factual manipulation, selective presentation, emotional manipulation, logical manipulation,
authority manipulation, repetition/amplification within material, and strategic persuasion.
Secondary labels are allowed. A single technique alone does not establish a material verdict.

Negatives include neutral reporting, ordinary advocacy, legitimate emotion, accurate authority,
educational discussion, rejected quotations, and necessary repetition. Keep ambiguous cases in
a separate auxiliary set; never count uncertainty as a confident negative.

Define scenario, audience, genre, length, reference facts, intended family, speaker/stance,
and expected evidence before prose generation. Balance topics and styles across categories.
Factual distortion needs reference facts; selective presentation needs comparison evidence.
Synthetic sources must be labeled fixtures, never fabricated public citations.

Use Luna for candidate generation and a separate Sol annotation pass blinded to intended
class. Use Jev checks and adjudicate disagreements. Reject/regenerate weak candidates to
meet quotas. Store generator intent, reference annotations, and application predictions separately.

Each annotation records material label, dominant/secondary families, techniques, exact spans,
stance, rationale, evidence, ambiguity, review status, and model/prompt/rubric versions.
AI-assisted labels are not human-reviewed ground truth.

## Partitions

| Split | Negatives | Each of seven positive families | Total |
|---|---:|---:|---:|
| Development | 270 | 90 | 900 |
| Validation | 90 | 30 | 300 |
| Held-out test | 90 | 30 | 300 |

Split scenario families before generation. Keep paraphrases and shared evidence together.
Check exact and near duplicates. Tune only on development/validation; freeze test data before
final evaluation. Record manifests, seeds, hashes, generation versions, and rejected candidates.

## Collected web set

Target 300 additional public materials, separate from synthetic quotas and initially held out
from model selection. Include sources credibly reported to disseminate propaganda, other public
organizations/accounts, primary-source reporting, and matched benign controls, including
controls from the same publishers. Reputation is a sampling attribute, never a content label.
Keep supporting citations for source characterizations separate from material judgments.

Record URLs, author if known, dates, language, acquisition method, hashes, and redistribution
conditions. Do not bypass access restrictions. Package permitted excerpts and references where
full redistribution is unsuitable. Blind reputation and pipeline predictions during annotation
where practical while retaining necessary speaker context. Preserve uncertain classifications.
Assistant judgments must be marked AI-assisted; require actual human review before calling
labels human-reviewed or expert gold. Do not force collected material into class quotas.

## Evaluation and optional tree

Run a small generation/evaluation pilot first; measure quality, latency, and API usage before
resumable full batches. Report synthetic and collected results separately. Include per-family
precision/recall/F1, material confusion, negative false-positive rate, abstention rate, coverage,
escalation rate, latency, and annotation provenance. Never tune on the held-out test set.

Optional local training: one CPU decision tree over scores, missingness flags, coverage,
evidence completeness, contradiction counts, attribution, and supported technique statistics.
Exclude publisher reputation, generation metadata, reference labels, and split identifiers.
Train preprocessing on development only. Search depths 3/4/5 and leaf minimums 10/20 on
validation. Retain baseline rules unless the tree improves validation without increasing benign
false positives. Freeze the selected policy before final testing. Show exact decision paths;
leaf frequencies are not calibrated propaganda probabilities. No neural training or fine-tuning.
