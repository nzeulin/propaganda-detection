# Demonstration runbook

## Current application

From the repository root, run `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
and `npm run dev --prefix frontend` in separate terminals. Open http://127.0.0.1:5173.
Configure provider keys in ignored `.env`; restart the backend after changes. Keys must never
appear in frontend bundles, reports, screenshots, or version control.

The current demos cover informational content and a manipulative town-hall fixture. Arbitrary
text uses live providers. Inspect highlights and diagnostic scores. The architecture view is
currently a static worked example, not the planned interactive system explorer.

## Planned complete demonstration — not yet available

Fresh local Docker startup → labeled synthetic dataset → content and mandatory fact check →
exact claim/evidence inspection → automatic deeper verification example → coordinated network
and timestamps → organic control → dismiss false positive → reload review history → trace
replay → evaluation error inspection → JSON/print export.

Rehearse unavailable providers, cancellation, restart, and offline replay. Keep synthetic source
packets and live evidence visibly distinct. Public Hostinger deployment is a later milestone.
