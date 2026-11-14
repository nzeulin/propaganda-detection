# Packaged demonstration data

- `demo_network.json`: 172 explicitly synthetic observations, including two recurrent
  three-account groups and ordinary background activity. Import as a JSON event array.
- `synthetic_pilot.jsonl`: 40 development-only synthetic references: 12 clear negatives
  and four for each of seven dominant families. Luna generation; independent Sol
  annotation receives only opaque IDs, text and reference/comparison facts; Jev quality
  checks. This is a pilot, not the planned 1,500-record corpus.
- `demo_predictions.jsonl`: six saved application executions for accepted pilot records.
  These preserve observed failures and abstentions; they are not illustrative scores.
- `web_corpus.jsonl`, `web_manifest.json`: 300 public RSS headline/lede excerpts, acquisition
  metadata and AI-assisted annotations. Scope is the short excerpt, not the unseen article.
  Source reputation was excluded from annotation inputs. Uncertainty is retained.

The two fixed content examples in `app/content/examples.py` are explicitly labeled fixtures.
All reference labels are AI-assisted, not human expert gold. Publisher rights remain with
publishers; the web set contains short excerpts and references, not full articles.

Runtime corpus/prediction files under `.local-data/` take precedence over these packaged
examples. The full corpus and expanded validation are being developed on
`implementation/full-plan`; no complete-corpus accuracy claim is made on `main`.
