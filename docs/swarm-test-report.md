# Swarm MVP test report

Tested locally on 2026-11-14 using Python 3.12.3 and the current uncommitted implementation. Application code was not changed during this test pass. Nothing was committed or pushed.

## Outcome

**38 backend checks passed; 4 failed, exposing 3 input-validation issues.** The original 22-check suite remains green; 20 additional boundary checks were added. Both browser suites passed. The main investigation flow works, but API input validation is not fully robust.

| Check | Result |
| --- | --- |
| Original backend regressions | 22 passed |
| Additional backend boundaries | 16 passed, 4 failed |
| Backend lint and Python compilation | Passed |
| TypeScript, including unchecked side-effect imports | Passed |
| Production frontend build | Passed |
| Real browser/API smoke suite | Passed |
| Browser resilience suite | Passed |
| Whitespace / unresolved merge conflicts | Clean / none |

The combined backend run completed in 2.35 seconds. The 5,000-row **sparse** import/analysis check took about 0.23 seconds locally; this is not a dense-input or concurrent-load benchmark.

## Confirmed defects

### 1. Duplicate CSV headers silently discard data

**Location:** [CSV reader construction](../app/core/ingestion.py#L95).

Submit CSV with the header `account_id,account_id,content_id,action,text` and the row `a,b,p,created,alpha beta gamma delta`. The API returns **201** and stores account `b`, silently dropping account `a`. Expected: **422**, rejecting ambiguous headers. The browser's own CSV validator rejects duplicate headers, but direct API imports do not.

### 2. Oversized CSV fields return an internal server error

**Location:** [CSV iteration](../app/core/ingestion.py#L97).

Submit a CSV text cell containing 131,073 characters, still well below the advertised 10 MB import limit. The Python CSV parser raises an uncaught `csv.Error`, producing **500**. Expected: **422** with a controlled validation message. The text cell exceeds the separate 40,000-character content limit and should be rejected, not accepted or allowed to cause a server error.

### 3. Timestamp timezone normalization can overflow

**Location:** [UTC conversion](../app/core/ingestion.py#L38).

Either `0001-01-01T00:00:00+14:00` or `9999-12-31T23:59:59-14:00` causes UTC normalization to raise an uncaught `OverflowError`, producing **500**. Expected: **422** because the normalized instant is outside the supported datetime range. These are two failing parameterized cases of one defect.

The failures are retained as ordinary failing regression assertions, not skipped or marked as expected failures.

## Additional verified behavior

- Exactly 5,000 sparse rows import and analyze; 5,001 JSON/CSV rows and imports exceeding the encoded 10 MB limit are rejected.
- Duplicate observations do not inflate recurrence; equivalent timezone offsets normalize consistently.
- Matching includes a separation of exactly 60 seconds and excludes 60.001 seconds. Episode boundaries follow the documented inactivity rule.
- URL-only evidence has finite scores and source previews. Missing content is excluded before evidence hydration.
- Partial shuffled baselines are reported and cannot produce strong claims.
- Invalid tail rows do not partially persist imports. Graph caps preserve valid edge endpoints, and time filters suppress inferred links.
- Cancelling an already-running job reaches its cooperative worker and saves no analysis. This is separate from the older queued-job cancellation check.
- Browser smoke checks cover all three examples, source evidence, graph rendering, JSON export, invalid JSON and CSV upload.
- Browser resilience checks cover HTTP 503/network failures, no automatic retry, preserved previous results, unavailable examples with manual upload, BOM/CRLF/multiline/escaped-quote CSV, safe text rendering of HTML-like input, zoom controls and 390px mobile sizing.
- The browser cancellation-wiring scenario uses controlled transport responses; the Python API test separately exercises a real running worker's cancellation signal.

## Local test artifacts

Internal tests remain ignored under the existing repository convention:

- [Original backend suite](../.copilot-cache/test_swarm.py)
- [New boundary suite and failure reproductions](../.copilot-cache/test_swarm_boundaries.py)
- [Browser smoke suite](../.copilot-cache/browser/swarm-smoke.mjs)
- [Browser resilience suite](../.copilot-cache/browser/swarm-resilience.mjs)

Run the backend suites together with `.venv/bin/python -m pytest .copilot-cache/test_swarm.py .copilot-cache/test_swarm_boundaries.py -q`. Run each browser script with Node from the repository root while the API serves the built UI on port 8000. Browser runs save synthetic datasets/jobs in local application storage; Python API tests use isolated temporary SQLite databases and disabled provider credentials.

These tests establish behavior on synthetic and boundary inputs, not real-world bot-detection accuracy, precision, recall or false-positive rates. Production authentication, abuse prevention, retention and deployment hardening remain outside this test pass.