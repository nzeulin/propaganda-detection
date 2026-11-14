import { useEffect, useState, type ReactNode } from "react";
import { PostScoring, usePostScoring } from "./PostScoring";
import type { CollectionInfo, Selection, Snapshot, SwarmResult, request as requestApi } from "./SwarmNetwork";

export type ConnectivityPair = {
  id: string;
  source_id: string;
  target_id: string;
  mention: boolean;
  similarity: number;
  score: number;
  weight: number;
  evidence?: { total: number; items: {
    author_id: string; mentioned_id: string; material_id: string;
    source: string; excerpt: string | null;
  }[] };
};

export type ConnectivityResult = {
  mode: "agent_connectivity";
  analysis_id: string;
  status: "complete" | "insufficient_data";
  collection?: CollectionInfo;
  clusters: { id: string; account_ids: string[] }[];
  account_labels: Record<string, string>;
  agent_features: Record<string, { material_count: number; material_ids: string[];
    previews: { id: string; text: string; url: string | null }[] }>;
  counts: { accounts: number; materials: number; pair_comparisons: number; connected_pairs: number; isolated_agents: number };
  parameters: { threshold: number; model: string; dimensions: number; version: string };
  formula: string;
  warnings: string[];
  limitations: string[];
};

export function isConnectivity(result: SwarmResult | ConnectivityResult): result is ConnectivityResult {
  return result.mode === "agent_connectivity";
}

export function ConnectivitySummary({ snapshot, exportResult, coverage }: {
  snapshot: Snapshot<ConnectivityResult>; exportResult: () => void; coverage?: ReactNode;
}) {
  const { result } = snapshot;
  return <section className="swarm-panel swarm-result-summary" aria-label="Agent connectivity result">
    <header className="swarm-panel-heading"><h3>{snapshot.name}</h3>
      <button type="button" onClick={exportResult}>Export result JSON ↓</button></header>
    <div className="swarm-panel-body">
      <p className="swarm-muted">Source: {snapshot.provenance}. Connectivity threshold: {result.parameters.threshold.toFixed(2)}.</p>
      <p className="swarm-takeaway">{result.clusters.length
        ? `${result.clusters.length} connected agent ${result.clusters.length === 1 ? "group" : "groups"}.`
        : "No connected agent groups at this threshold."}</p>
      <dl className="swarm-metrics swarm-counts">
        {[
          ["Agents", result.counts.accounts], ["Authored materials", result.counts.materials],
          ["Connected pairs", result.counts.connected_pairs], ["Isolated agents", result.counts.isolated_agents],
        ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value.toLocaleString()}</dd></div>)}
      </dl>
      {result.status === "insufficient_data" && <p className="swarm-notice">Add another attributed agent to compare connections.</p>}
      {result.warnings.map((warning, index) => <p className="swarm-notice" key={index}>{warning}</p>)}
      <details className="swarm-result-details"><summary>Result details</summary>
        <p>Connections combine an explicit mention bonus with similarity between agents’ authored content. A connected chain forms a group; every pair in that group need not be directly connected.</p>
        <p>Content similarity and references do not establish coordinated behavior or bot identity.</p>
        <p className="swarm-formula">{result.formula}</p>
        <p>{result.counts.pair_comparisons.toLocaleString()} pairs compared over the full dataset. Model: {result.parameters.model}; {result.parameters.dimensions} dimensions. Policy: {result.parameters.version}.</p>
        {coverage}
      </details>
    </div>
  </section>;
}

type PairPage = { total: number; items: ConnectivityPair[] };

export function ConnectivityEvidence({ snapshot, selection, select, open, onClose, load }: {
  snapshot: Snapshot<ConnectivityResult>; selection: Selection | null; select: (value: Selection) => void;
  open: boolean; onClose: () => void; load: typeof requestApi;
}) {
  const { result } = snapshot;
  const { scores } = usePostScoring();
  const [pagination, setPagination] = useState({ key: "", offset: 0 });
  const [page, setPage] = useState<PairPage>({ total: 0, items: [] });
  const [pair, setPair] = useState<ConnectivityPair | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const key = `${selection?.kind}:${selection?.id}`;
  const offset = pagination.key === key ? pagination.offset : 0;
  const node = selection?.kind === "entity" ? snapshot.graph.nodes.find(item => item.id === selection.id) : undefined;
  const previewOwner = selection?.kind === "entity" ? Object.entries(result.agent_features)
    .find(([, feature]) => feature.previews.some(item => item.id === selection.id)) : undefined;
  const preview = previewOwner?.[1].previews.find(item => item.id === selection?.id);
  const authorId = node?.kind === "content" ? node.data.author_id : previewOwner?.[0];
  const agentId = selection?.kind === "entity" ? authorId || selection.id : undefined;
  const label = (id: string) => result.account_labels[id] || snapshot.graph.nodes.find(item => item.id === id)?.data.source_id || id;

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ offset: String(offset), limit: "50" });
    if (selection?.kind === "cluster") params.set("group_id", selection.id);
    if (selection?.kind === "entity" && agentId) params.set("agent_id", agentId);
    setBusy(true);
    setError("");
    load<PairPage>(`/agent-connectivity/${encodeURIComponent(result.analysis_id)}/pairs?${params}`, {}, controller.signal)
      .then(value => { if (!controller.signal.aborted) setPage(value); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not load pairs."); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [key, agentId, offset, retry, result.analysis_id, load]);

  useEffect(() => {
    const controller = new AbortController();
    setPair(null);
    if (selection?.kind === "pair") {
      load<PairPage>(`/agent-connectivity/${encodeURIComponent(result.analysis_id)}/pairs?pair_id=${encodeURIComponent(selection.id)}&limit=1`, {}, controller.signal)
        .then(value => { if (!controller.signal.aborted) setPair(value.items[0] || null); })
        .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not load pair evidence."); });
    }
    return () => controller.abort();
  }, [key, retry, result.analysis_id, load]);

  const group = selection?.kind === "cluster" ? result.clusters.find(item => item.id === selection.id) : undefined;
  return <>
    <details className="swarm-panel swarm-selection swarm-evidence-picker" id="swarm-evidence">
      <summary>Explore evidence</summary>
      <div className="swarm-panel-body">
        <h4>Connected groups</h4>
        <div className="swarm-groups">{result.clusters.map((item, index) => <button type="button" key={item.id}
          aria-pressed={selection?.kind === "cluster" && selection.id === item.id}
          onClick={() => select({ kind: "cluster", id: item.id })}>
          <span>Group {index + 1}</span><span>{item.account_ids.length} agents connected by paths</span>
        </button>)}</div>
        {!result.clusters.length && <p className="swarm-muted">No groups at this threshold. Isolated agents remain in the map.</p>}
        <label className="swarm-field" htmlFor="swarm-entity">Browse agents &amp; materials</label>
        <select id="swarm-entity" value={selection?.kind === "entity" && node ? selection.id : ""}
          onChange={event => { if (event.target.value) select({ kind: "entity", id: event.target.value }); }}>
          <option value="">Select an item…</option>
          {snapshot.graph.nodes.map(item => <option key={item.id} value={item.id}>{item.kind === "account" ? "agent" : "material"} / {label(item.id)}</option>)}
        </select>
        <h4>Pair scores</h4>
        {busy ? <p role="status">Loading agent pairs…</p> : <>
          <p className="swarm-muted">{page.total.toLocaleString()} pairs in this view. Zero-weight pairs are not drawn or used for grouping.</p>
          <div className="swarm-pair-list">{page.items.map(item => <button type="button" key={item.id}
            aria-pressed={selection?.kind === "pair" && selection.id === item.id}
            onClick={() => select({ kind: "pair", id: item.id, source_id: item.source_id, target_id: item.target_id })}>
            <span>{label(item.source_id)} ↔ {label(item.target_id)}</span><small>{item.score.toFixed(3)} / 2</small>
          </button>)}</div>
          <div className="swarm-actions">
            <button type="button" disabled={offset === 0} onClick={() => setPagination({ key, offset: Math.max(0, offset - 50) })}>Previous pairs</button>
            <button type="button" disabled={offset + page.items.length >= page.total} onClick={() => setPagination({ key, offset: offset + 50 })}>Next pairs</button>
          </div>
        </>}
        {error && <div role="alert" className="swarm-error"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Retry evidence</button></div>}
        {selection && !open && <button type="button" onClick={() => select(selection)}>Open selected evidence →</button>}
      </div>
    </details>
    {open && <aside className={`swarm-panel swarm-inspection ${selection?.kind === "entity" && scores[selection.id]?.screening?.label === "requires_further_analysis" ? "swarm-needs-validation" : ""}`} aria-label="Agent connectivity inspector">
      <header className="swarm-panel-heading"><span>Connection evidence</span><button type="button" aria-label="Close evidence panel" onClick={onClose}>Close ×</button></header>
      <div className="swarm-panel-body">
        {group && <><h3>Connected agent group</h3><p>{group.account_ids.length} agents connected through paths. This does not require a direct connection between every pair.</p>
          <div className="swarm-members">{group.account_ids.map(id => <button type="button" key={id} onClick={() => select({ kind: "entity", id })}>{label(id)}</button>)}</div>
          <p>Select a pair in Explore evidence to inspect its score.</p></>}
        {selection?.kind === "entity" && <>
          <h3>{label(selection.id)}</h3>
          {(node?.data.text || preview?.text) && <p className="swarm-entity-text">{node?.data.text || preview?.text}</p>}
          {(node?.kind === "content" || preview) && <PostScoring contentId={selection.id} />}
          {node?.data.source_post_url && <p><a href={node.data.source_post_url} target="_blank" rel="noopener noreferrer">Open original material ↗</a></p>}
          {result.agent_features[selection.id] && <>
            <p>{result.agent_features[selection.id].material_count} authored materials contributed to this agent’s vector. Reposts and likes are excluded.</p>
            <MaterialPreviews features={result.agent_features[selection.id]} select={select} />
          </>}
        </>}
        {selection?.kind === "pair" && (pair ? <>
          <h3>{label(pair.source_id)} ↔ {label(pair.target_id)}</h3>
          <dl className="swarm-metrics">
            <div><dt>Direct mention</dt><dd>{Number(pair.mention)} / 1</dd></div>
            <div><dt>Nonnegative cosine similarity</dt><dd>{pair.similarity.toFixed(3)} / 1</dd></div>
            <div><dt>Connectivity</dt><dd>{pair.score.toFixed(3)} / 2</dd></div>
            <div><dt>Normalized line weight</dt><dd>{pair.weight.toFixed(3)} / 1</dd></div>
          </dl>
          <p className="swarm-formula">{Number(pair.mention)} + {pair.similarity.toFixed(3)} = {pair.score.toFixed(3)}</p>
          <p>{pair.weight > 0 ? "This connection is above the run’s threshold." : "This pair has no visible connection at the run’s threshold."} Repeated or mutual mentions add at most one point.</p>
          <h4>Mention evidence</h4>
          {!pair.mention && <p>No explicit mention was found in the imported authored materials.</p>}
          {pair.evidence?.items.map(item => <div key={`${item.material_id}:${item.mentioned_id}`} className="swarm-notice">
            <p>{label(item.author_id)} → {label(item.mentioned_id)} · {item.source.replaceAll("_", " ")}</p>
            {item.excerpt ? <blockquote>{item.excerpt}</blockquote> : <p>Explicitly declared by the material’s imported mention IDs.</p>}
            <p className="swarm-muted">Material: {item.material_id}</p>
          </div>)}
          {(pair.evidence?.total || 0) > (pair.evidence?.items.length || 0) && <p>Showing {pair.evidence?.items.length} of {pair.evidence?.total} mentioning materials.</p>}
          {[pair.source_id, pair.target_id].map(id => <details key={id}><summary>Authored material for {label(id)}</summary>
            <MaterialPreviews features={result.agent_features[id]} select={select} />
          </details>)}
        </> : <p role="status">{error || "Loading connection evidence…"}</p>)}
      </div>
    </aside>}
  </>;
}

function MaterialPreviews({ features, select }: {
  features: ConnectivityResult["agent_features"][string]; select: (value: Selection) => void;
}) {
  return <div>
    <p className="swarm-muted">Showing {features.previews.length} previews of {features.material_count} materials. Similarity compares the complete authored-material average.</p>
    {features.previews.map(material => <div key={material.id} className="swarm-notice">
      <p>{material.text}</p>
      <button type="button" onClick={() => select({ kind: "entity", id: material.id })}>Inspect material</button>
      {material.url && /^https?:\/\//i.test(material.url) && <p><a href={material.url} target="_blank" rel="noopener noreferrer">Original source ↗</a></p>}
    </div>)}
  </div>;
}
