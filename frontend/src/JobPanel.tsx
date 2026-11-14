import { useEffect, useState } from "react";
import { api, type Analysis } from "./types";
import { Results } from "./Results";
import type { components } from "./contracts";

export type Trace = {
  module: string;
  status: string;
  started_at: string;
  elapsed_seconds: number;
  provider: string;
  inputs: Record<string, unknown>;
  artifact: unknown;
};
export type Evidence = {
  source_id: string;
  url: string;
  excerpt: string;
  start: number;
  end: number;
};
export type Verification = {
  status: string;
  model: string;
  escalated: boolean;
  escalation_reasons: string[];
  search_calls: number;
  fetch_count: number;
  checks: {
    claim_id: string;
    kind: string;
    explanation: string;
    evidence: Evidence[];
    comparison_evidence: Evidence[];
    relation: { choice: string; confidence: number };
  }[];
  sources: {
    id?: string;
    url?: string;
    title?: string;
    status: string;
    requested_url: string;
    retrieved_at: string;
    content_sha256?: string;
  }[];
};
export type Finding = {
  id: string;
  source_id: string;
  target_id: string;
  score: number;
  strong: boolean;
  episode_count: number;
  baseline_max: number;
  episodes: {
    event_ids: string[];
    separation_seconds: number;
    lexical_similarity: number;
    shared_urls: string[];
  }[];
};
export type Swarm = {
  status?: string;
  warnings?: string[];
  findings: Finding[];
  clusters: { id: string; account_ids: string[]; density: number }[];
  formula: string;
  limitations: string[];
};
export type Job = Omit<
  components["schemas"]["JobRecord"],
  "trace" | "result" | "error"
> & {
  id: string;
  kind: string;
  target_id: string;
  status: string;
  created_at: string;
  trace: Trace[];
  error: { category: string; message: string } | null;
  result:
    | (Analysis &
        Swarm & {
          analysis_id: string;
          verification?: Verification;
          investigation_status?: string;
        })
    | null;
};

export function JobPanel({
  id,
  onChange,
  onComplete,
}: {
  id: string;
  onChange: (id: string) => void;
  onComplete?: (job: Job) => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setJob(null);
    setError("");
    async function poll() {
      try {
        const value = await api<Job>(
          `/api/v1/jobs/${id}`,
          undefined,
          abort.signal,
        );
        setJob(value);
        setNow(Date.now());
        if (["queued", "running"].includes(value.status))
          timer = setTimeout(poll, 1000);
        else onComplete?.(value);
      } catch (e) {
        if (!abort.signal.aborted) setError((e as Error).message);
      }
    }
    poll();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [id]);
  async function control(action: string) {
    try {
      const value = await api<Job>(`/api/v1/jobs/${id}/${action}`, {});
      setJob(value);
      onChange(value.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (!job) return <p role="status">{error || "Loading saved analysis…"}</p>;
  const partial = job.trace.find(
    (t) => t.module === "content" && t.status === "completed",
  )?.artifact as Analysis | undefined;
  const content = job.kind === "content" ? job.result || partial : null;
  const verification = job.result?.verification;
  return (
    <section className="job-section">
      <div className="panel job-progress" aria-live="polite">
        <div className="eyebrow">
          PERSISTENT {job.kind.toUpperCase()} ANALYSIS
        </div>
        <div className="toolbar">
          <h2>{job.status.replaceAll("_", " ")}</h2>
          {["queued", "running"].includes(job.status) && (
            <button className="sample" onClick={() => control("cancel")}>
              Cancel analysis
            </button>
          )}
          {["failed", "cancelled", "interrupted"].includes(job.status) && (
            <button className="sample" onClick={() => control("retry")}>
              Retry explicitly
            </button>
          )}
          {job.result && (
            <>
              <button
                className="sample"
                onClick={() => {
                  const url = URL.createObjectURL(
                    new Blob([JSON.stringify(job, null, 2)], {
                      type: "application/json",
                    }),
                  );
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `analysis-${job.id}.json`;
                  a.click();
                  setTimeout(() => URL.revokeObjectURL(url), 1000);
                }}
              >
                Export JSON
              </button>
              <button className="sample" onClick={() => window.print()}>
                Print report
              </button>
              <a className="sample" href={`#system?job=${job.id}`}>
                Explore this execution ↗
              </a>
            </>
          )}
        </div>
        <ol className="stage-strip">
          {job.trace.map((stage, i) => (
            <li key={i} className={stage.status}>
              <strong>{stage.module.replaceAll("_", " ")}</strong>
              <span>
                {stage.status} ·{" "}
                {stage.status === "running"
                  ? Math.max(
                      0,
                      (now - Date.parse(stage.started_at)) / 1000,
                    ).toFixed(0)
                  : stage.elapsed_seconds.toFixed(1)}
                s · {stage.provider}
              </span>
            </li>
          ))}
        </ol>
        {!job.trace.length && <p>Waiting for one of two local worker slots.</p>}
        {job.error && (
          <p role="alert" className="error">
            {job.error.message}
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <p className="small muted">
          You can reload this page. Completed stages are saved locally. Retrying
          may incur provider charges.
        </p>
      </div>
      {content && (
        <>
          <Results result={content} />
          {!verification && !content.demo && (
            <p className="panel">
              Text indicators are available. Factual verification is{" "}
              {job.status === "running" ? "still running" : "incomplete"};
              investigation needs review.
            </p>
          )}
        </>
      )}
      {verification && (
        <section className="panel verification-panel">
          <div className="eyebrow">SOL + JEV / SOURCE EVIDENCE</div>
          <h2>Verification: {verification.status.replaceAll("_", " ")}</h2>
          <p>
            {verification.search_calls} search calls ·{" "}
            {verification.fetch_count} fetch attempts ·{" "}
            {verification.escalated
              ? "Initial and deeper passes"
              : "Initial pass"}
          </p>
          {verification.escalated && (
            <p className="small muted">
              Deeper pass: {verification.escalation_reasons.join(" · ")}
            </p>
          )}
          {verification.checks.map((check) => (
            <details
              className="finding"
              key={check.claim_id}
              id={`claim-${check.claim_id}`}
            >
              <summary>
                {check.claim_id} · {check.kind} ·{" "}
                {check.kind === "factual"
                  ? check.relation.choice
                  : "Not a checkable factual assertion"}
              </summary>
              <p>
                {content?.statements.find((c) => c.id === check.claim_id)?.text}
              </p>
              <p>{check.explanation}</p>
              {[...check.evidence, ...check.comparison_evidence].map(
                (quote, i) => (
                  <blockquote key={i}>
                    {quote.excerpt}
                    <br />
                    <a
                      className="cyan"
                      href={
                        /^https?:\/\//.test(quote.url) ? quote.url : undefined
                      }
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open exact source ↗
                    </a>
                    <small>
                      {" "}
                      · source offsets {quote.start}–{quote.end}
                    </small>
                  </blockquote>
                ),
              )}
              {!check.evidence.length && (
                <p>
                  No verified exact source excerpt. This does not establish
                  falsehood.
                </p>
              )}
            </details>
          ))}
          <details>
            <summary>Source acquisition and provenance</summary>
            {verification.sources.map((s, i) => (
              <p className="small source-row" key={i}>
                {s.title || s.requested_url} · {s.status} · retrieved{" "}
                {s.retrieved_at}
                <br />
                <code>{s.content_sha256}</code>
              </p>
            ))}
          </details>
        </section>
      )}
      {job.kind === "swarm" && job.result && (
        <section className="panel">
          <div className="eyebrow">INDEPENDENT COORDINATION ANALYSIS</div>
          <h2>{job.result.clusters.length} suspicious groups</h2>
          {job.result.warnings?.map((w) => (
            <p className="error" key={w}>
              {w}
            </p>
          ))}
          <p>{job.result.formula}</p>
          {job.result.findings.map((f) => (
            <details className="finding" key={f.id}>
              <summary>
                {f.strong ? "Strong recurrent pair" : "Below threshold"} ·{" "}
                {f.episode_count} episodes · score {f.score.toFixed(3)} ·
                shuffled maximum {f.baseline_max}
              </summary>
              <p className="small source-row">
                Accounts: {f.source_id} ↔ {f.target_id}
              </p>
              {f.episodes.map((e, i) => (
                <p className="small source-row" key={i}>
                  Episode {i + 1}: {e.separation_seconds}s apart · lexical{" "}
                  {e.lexical_similarity.toFixed(3)} · events{" "}
                  {e.event_ids.join(" / ")}
                </p>
              ))}
            </details>
          ))}
          {job.result.limitations.map((l) => (
            <p className="small muted" key={l}>
              {l}
            </p>
          ))}
        </section>
      )}
    </section>
  );
}
