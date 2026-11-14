import { useEffect, useState } from "react";
import { api } from "./types";

type Dataset = { id: string; name: string; created_at: string };
type Node = {
  id: string;
  kind: string;
  data: { text?: string; source_id: string; platform?: string };
};
type Graph = {
  nodes: Node[];
  edges: {
    id: string;
    source_id: string;
    target_id: string;
    action: string;
    timestamp: string | null;
  }[];
  hidden_nodes: number;
};
type Review = {
  id: string;
  decision: string;
  reason: string;
  created_at: string;
};

export function Investigations() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState("");
  const [graph, setGraph] = useState<Graph | null>(null);
  const [node, setNode] = useState<Node | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [name, setName] = useState("");
  const [format, setFormat] = useState("text");
  const [input, setInput] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
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
    setGraph(null);
    setNode(null);
    setError("");
    if (!selected) return;
    const abort = new AbortController();
    api<Graph>(`/api/v1/datasets/${selected}/graph`, undefined, abort.signal)
      .then(setGraph)
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [selected]);
  useEffect(() => {
    setReviews([]);
    setReason("");
    if (!node) return;
    const abort = new AbortController();
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
      await api("/api/v1/feedback", { target_id: target, decision, reason });
      setReviews(await api<Review[]>(`/api/v1/feedback?target_id=${target}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review failed");
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
      </form>
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
        onChange={(e) => setSelected(e.target.value)}
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
            {graph.nodes.map((n) => (
              <button
                key={n.id}
                className="sample"
                disabled={busy}
                aria-pressed={node?.id === n.id}
                onClick={() => setNode(n)}
              >
                {n.kind}: {n.data.source_id}
              </button>
            ))}
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
          </section>
          <aside className="panel evidence-panel">
            <h2>Entity review</h2>
            {node ? (
              <>
                <p>{node.data.text || node.data.source_id}</p>
                <label className="field-label" htmlFor="review-reason">
                  Review reason
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
    </>
  );
}
