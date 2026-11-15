# Agent embeddings and connectivity

The network UI's **Analyze activity** sends original authored text to OpenAI for embeddings. Set `OPENAI_API_KEY`; TypeSafe is needed only for optional post scoring. Configure the model with `AGENT_EMBEDDING_MODEL` (default `text-embedding-3-small`). Embedding defaults and resource limits live in `config/agent_connectivity.yaml`.

Each material is split into nonoverlapping 2,048-token chunks. Its vector is the normalized, token-weighted average of chunk vectors. Each agent's vector is the normalized, equally weighted average of its authored material vectors. Reposts and likes do not contribute. Every eligible attributed agent needs authored text; URL-only material is not fetched or embedded. Runs accept at most 300 agents and reject larger datasets before embedding requests.

For each unordered pair:

```
similarity = max(0, cosine(agent_a, agent_b))
score = binary_mention + similarity                    # 0..2
weight = clamp((score - threshold) / (2 - threshold), 0, 1)
```

The mention bonus is one if either agent explicitly mentions the other in authored material. Repeated and mutual mentions still add only one; self mentions add nothing. Matching uses platform mention metadata, exact handles, Bluesky profile URLs or imported `mentioned_account_ids`. Targets must belong to the same dataset and platform. Bare names and fuzzy matches do not count. JSON imports accept an array of source account IDs; CSV accepts a JSON array in that field, with normal CSV quoting.

The threshold defaults to `0.5` and accepts `0 <= threshold < 2` in advanced options. It is frozen for each submitted run. Scores at or below it produce no connection. Positive connections are teal, with line width `4 * weight`; observed actions remain gray. Groups are connected components of two or more agents, so a chain forms a group without requiring every pair to connect. Isolated agents stay in the map. These signals do not establish coordination, shared ownership or bot identity; real-world quality has not been evaluated.

## API and persistence

- `POST /api/v1/swarm/analyze` with `{ "dataset_id": "...", "mode": "agent_connectivity", "connectivity_threshold": 0.5 }` submits a job. Omitting `mode` retains the existing CPU-only temporal API.
- Poll `GET /api/v1/jobs/{job_id}`. Successful results contain `analysis_id`, groups, counts, parameters and authored-material previews.
- `GET /api/v1/datasets/{dataset_id}/graph?connectivity_analysis_id={analysis_id}` overlays that completed revision's `connectivity_edges`. Grouping covers the full dataset before the existing 300-entity display cap.
- `GET /api/v1/agent-connectivity/{analysis_id}/pairs` returns score-ordered evidence, 50 pairs per page by default (`offset`, `limit`, optional `agent_id`, `group_id`, `pair_id`, `connected_only`). Mention evidence includes up to 20 materials per pair and its full count.
- `GET /api/v1/swarm/{dataset_id}/analysis?mode=agent_connectivity` retrieves the latest successful revision.

SQLite stores material vectors by original text, requested model, dimensions and policy version. Identical text can reuse a cached vector across materials and runs; threshold changes reuse embeddings. The result records the response-reported model. Concurrent jobs share a cache-generation lock. Completed material vectors survive later failures; incomplete materials are retried explicitly. Raw vectors are not included in job traces or evidence responses.

Missing credentials, authored text, invalid vectors or provider failures withhold the new result and preserve the previous graph. Jobs support cancellation and explicit retry. Reading graphs, evidence or saved analyses never calls a model. The legacy temporal detector and its API remain available; its groups and scores are separate from connectivity results.
