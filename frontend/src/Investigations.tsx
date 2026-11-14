import { useEffect, useState } from "react";
import { api } from "./types";
import {
  InvestigationGraph,
  type Graph,
  type GraphNode as Node,
} from "./InvestigationGraph";
import { JobPanel, type Job } from "./JobPanel";

type Dataset = { id: string; name: string; created_at: string };
type Review = {
  id: string;
  decision: string;
  reason: string;
  created_at: string;
};

export function Investigations() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState(
    () => localStorage.getItem("selected-investigation") || "",
  );
  const [graph, setGraph] = useState<Graph | null>(null);
  const [node, setNode] = useState<Node | null>(null);
  const [revision, setRevision] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [name, setName] = useState("");
  const [format, setFormat] = useState("text");
  const [input, setInput] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [focus, setFocus] = useState("");
  const [cluster, setCluster] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [jobId, setJobId] = useState("");
  const [swarmJob, setSwarmJob] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    api<Dataset[]>("/api/v1/datasets", undefined, abort.signal)
      .then(setDatasets)
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, []);
  useEffect(() => {
    setNode(null);
    localStorage.setItem("selected-investigation", selected);
    setSwarmJob(localStorage.getItem(`swarm-job-${selected}`) || "");
    setError("");
    if (!selected) return;
    const abort = new AbortController();
    api<Graph>(
      `/api/v1/datasets/${selected}/graph?${new URLSearchParams({ search, focus, cluster, ...(since ? { since: new Date(since).toISOString() } : {}), ...(until ? { until: new Date(until).toISOString() } : {}) })}`,
      undefined,
      abort.signal,
    )
      .then(setGraph)
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [selected, search, focus, cluster, since, until, refresh]);
  useEffect(() => {
    setReviews([]);
    setRevision(null);
    setJobId("");
    setReason("");
    if (!node) return;
    const abort = new AbortController();
    if (node.kind === "content") {
      const pending = localStorage.getItem(`content-job-${node.id}`);
      if (pending) setJobId(pending);
      else
        api<{ job_id: string; id: string }>(
          `/api/v1/content/${node.id}/analysis`,
          undefined,
          abort.signal,
        )
          .then((r) => {
            setJobId(r.job_id);
            setRevision(r.id);
          })
          .catch(() => {});
    }
    api<Review[]>(
      `/api/v1/feedback?target_id=${node.id}`,
      undefined,
      abort.signal,
    )
      .then(setReviews)
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [node]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await api<Dataset>("/api/v1/datasets", {
        name: name || "Untitled investigation",
        [format]: format === "rows" ? JSON.parse(input) : input,
      });
      setDatasets(await api<Dataset[]>("/api/v1/datasets"));
      setSelected(data.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }
  async function review(decision: string) {
    if (!node) return;
    const target = node.id;
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/feedback", {
        target_id: target,
        decision,
        reason,
        analysis_id: revision,
      });
      setReviews(await api<Review[]>(`/api/v1/feedback?target_id=${target}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }
  async function analyze(kind: "content" | "swarm") {
    setBusy(true);
    setError("");
    try {
      const job = await api<Job>(
        `/api/v1/${kind}/analyze`,
        kind === "content"
          ? { content_id: node!.id }
          : { dataset_id: selected },
      );
      if (kind === "content") {
        setJobId(job.id);
        localStorage.setItem(`content-job-${node!.id}`, job.id);
      } else {
        setSwarmJob(job.id);
        localStorage.setItem(`swarm-job-${selected}`, job.id);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-intro">
        <div className="eyebrow">SAVED OBSERVATIONS</div>
        <h1>Investigations</h1>
        <p>
          Import source observations and preserve your review decisions.
          Importing does not run model analysis.
        </p>
      </div>
      <details className="import-drawer" open={!selected}>
        <summary>Import a new investigation</summary>
        <form className="panel input-panel" onSubmit={save}>
          <label className="field-label" htmlFor="dataset-name">
            Investigation name
          </label>
          <input
            id="dataset-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            disabled={busy}
          />
          <label className="field-label" htmlFor="import-format">
            Input format
          </label>
          <select
            id="import-format"
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            disabled={busy}
          >
            <option value="text">Plain text</option>
            <option value="url">Public article URL</option>
            <option value="csv">CSV events</option>
            <option value="rows">JSON event array</option>
          </select>
          <p className="small muted">
            Event fields: account_id, content_id, action, timestamp, text, url,
            reply_to_content_id. Actions: created, reposted, replied_to, liked.
            Timestamps must include a UTC offset. Maximum 5,000 events / 10 MB.
          </p>
          <label className="field-label" htmlFor="dataset-input">
            Source observations
          </label>
          <textarea
            id="dataset-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            required
            disabled={busy}
          />
          <button className="primary" disabled={busy || !input.trim()}>
            {busy ? "Saving…" : "Save investigation"}
          </button>
          <label className="field-label" htmlFor="import-file">
            Or load a local text / CSV / JSON file
          </label>
          <input
            id="import-file"
            type="file"
            accept=".txt,.csv,.json"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              if (file.size > 10000000) {
                setError("Import exceeds 10 MB");
                return;
              }
              setInput(await file.text());
              setFormat(
                file.name.endsWith(".csv")
                  ? "csv"
                  : file.name.endsWith(".json")
                    ? "rows"
                    : "text",
              );
            }}
          />
        </form>
      </details>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <label className="field-label" htmlFor="saved-dataset">
        Saved investigations
      </label>
      <select
        id="saved-dataset"
        value={selected}
        onChange={(e) => {
          setSelected(e.target.value);
          setSearch("");
          setFocus("");
          setCluster("");
          setSince("");
          setUntil("");
        }}
        disabled={busy}
      >
        <option value="">Select an investigation</option>
        {datasets.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>
      {graph && (
        <div className="article-layout" style={{ marginTop: 24 }}>
          <section className="panel article-panel">
            <h2>Observed entities</h2>
            <p>
              {graph.nodes.length} visible entities · {graph.edges.length}{" "}
              visible actions · {graph.hidden_nodes} hidden entities
            </p>
            <div className="graph-filters">
              <label>
                Search observations
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Account, phrase, URL…"
                />
              </label>
              <label>
                From (local time)
                <input
                  type="datetime-local"
                  value={since}
                  onChange={(e) => setSince(e.target.value)}
                />
              </label>
              <label>
                Until (local time)
                <input
                  type="datetime-local"
                  value={until}
                  onChange={(e) => setUntil(e.target.value)}
                />
              </label>
              <label>
                Coordination group
                <select
                  value={cluster}
                  onChange={(e) => setCluster(e.target.value)}
                >
                  <option value="">All groups</option>
                  {graph.clusters.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id} · {c.account_ids.length} accounts
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="toolbar">
              <button
                className="sample"
                onClick={() => {
                  setSearch("");
                  setFocus("");
                  setCluster("");
                  setSince("");
                  setUntil("");
                }}
              >
                Reset filters
              </button>
              <button
                className="sample"
                disabled={!node}
                onClick={() => {
                  setFocus(node!.id);
                  setSearch("");
                  setCluster("");
                }}
              >
                Explore selected neighborhood
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() => analyze("swarm")}
              >
                Analyze coordination
              </button>
            </div>
            <InvestigationGraph
              graph={graph}
              selected={node?.id || null}
              onSelect={setNode}
            />
            <details>
              <summary>
                Observed action timeline / inferred relationships
              </summary>
              <h3>Observed relationships</h3>
              <ul>
                {graph.edges.map((e) => (
                  <li key={e.id}>
                    {
                      graph.nodes.find((n) => n.id === e.source_id)?.data
                        .source_id
                    }{" "}
                    → {e.action} →{" "}
                    {
                      graph.nodes.find((n) => n.id === e.target_id)?.data
                        .source_id
                    }{" "}
                    · {e.timestamp || "Time unknown"}
                  </li>
                ))}
              </ul>
            </details>
          </section>
          <aside className="panel evidence-panel">
            <h2>Entity review</h2>
            {node ? (
              <>
                <p className="source-row">
                  {node.data.text || node.data.source_id}
                </p>
                {node.kind === "content" && (
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => analyze("content")}
                  >
                    Analyze selected content
                  </button>
                )}
                <label className="field-label" htmlFor="review-reason">
                  {revision
                    ? "Review this analysis revision"
                    : "Review source observation"}
                </label>
                <textarea
                  id="review-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={4000}
                  disabled={busy}
                />
                {(["confirm", "dismiss", "needs_review"] as const).map((d) => (
                  <button
                    className="sample"
                    disabled={busy}
                    key={d}
                    onClick={() => review(d)}
                  >
                    {d.replaceAll("_", " ")}
                  </button>
                ))}
                <h3>Review history</h3>
                <ul>
                  {reviews.map((r) => (
                    <li key={r.id}>
                      {r.decision.replaceAll("_", " ")} ·{" "}
                      {r.reason || "No reason supplied"} · {r.created_at}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p>Select an entity to inspect its source and review history.</p>
            )}
          </aside>
        </div>
      )}
      {jobId && (
        <JobPanel
          id={jobId}
          onComplete={(job) => setRevision(job.result?.analysis_id || null)}
          onChange={(id) => {
            setJobId(id);
            if (node) localStorage.setItem(`content-job-${node.id}`, id);
          }}
        />
      )}
      {swarmJob && (
        <JobPanel
          id={swarmJob}
          onChange={(id) => {
            setSwarmJob(id);
            localStorage.setItem(`swarm-job-${selected}`, id);
          }}
          onComplete={(job) => {
            if (job.status === "completed") setRefresh((r) => r + 1);
          }}
        />
      )}
    </>
  );
}
