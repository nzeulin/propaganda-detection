# Verification record

The full release is NOT implemented or verified. See implementation_plan.md for pending gates.
The previously recorded baseline at commit 527857b passed 14 existing backend tests, three
additional checks, frontend type checking/build, browser regressions, and three live examples.
These historical results do not validate planned persistence, verification, swarm, or evaluation.

Reproduction commands for existing local checks:

```bash
.venv/bin/python -m pytest .copilot-cache -q
.venv/bin/python -m pytest .copilot-cache/.tests -q
.venv/bin/ruff check app
npm run check --prefix frontend
npm run build --prefix frontend
```

Future records must include commit, machine, dataset hash/split, commands, observed outcomes,
provider/model versions, timings, API usage, failures, and unresolved limitations. Live checks
must remain separate from deterministic fixtures. Never mark planned tests as passing.
