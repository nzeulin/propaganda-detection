# Project structure

## Current maintained modules

```text
app/__init__.py
app/content/__init__.py
app/content/aggregation.py
app/content/config.py
app/content/examples.py
app/content/ingestion.py
app/content/pipeline.py
app/content/policy.py
app/content/schemas.py
app/content/validation.py
app/main.py
app/providers/__init__.py
app/providers/jev.py
app/providers/live.py
app/providers/luna.py
app/providers/runtime.py
config/policy.yaml
config/prompts.yaml
config/roles.yaml
config/rubrics.yaml
config/taxonomy.yaml
docs/README.md
docs/content_classifier.md
docs/dataset_and_evaluation.md
docs/demo_runbook.md
docs/frontend.md
docs/implementation_plan.md
docs/propaganda_detection_project_outline.md
docs/task.md
docs/verification.md
frontend/src/highlights.ts
frontend/src/main.tsx
frontend/src/style.css
frontend/src/types.ts
```

Root manifests: pyproject.toml, requirements.lock, frontend/package.json, frontend/package-lock.json, frontend/tsconfig.json, frontend/vite.config.ts, .env.example, README.md.

app/content owns normalization, anchoring, attribution, aggregation and policy. app/providers owns bounded API adapters. frontend/src owns the current analyzer and worked example. config versions rubrics and prompts.

## Target structure

See the authoritative [implementation plan](implementation_plan.md). Add app/api, core, evidence, swarm, evaluation; split frontend into pages, components and generated API contracts; add migrations, scripts, data manifests, Dockerfile and compose.yaml as functionality is implemented.

Runtime artifacts: .local-data (planned SQLite/cache); .copilot-cache (ignored checks/browser tools); .venv and frontend/node_modules (dependencies); frontend/dist (generated build). Never commit .env or private runtime data.
