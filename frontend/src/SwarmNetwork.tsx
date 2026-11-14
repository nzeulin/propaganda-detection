/// <reference types="vite/client" />
import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { parseBlueskyProfiles } from "./blueskyProfiles";
import "./SwarmNetwork.css";

type InputFormat = "json" | "csv";
type InputRow = Record<string, unknown>;
type Example = {
  id: string;
  name: string;
  description: string;
  synthetic: true;
  rows: InputRow[];
};
type Entity = {
  id: string;
  kind: "account" | "content";
  data: { source_id: string; text?: string; url?: string; platform?: string; handle?: string; source_post_url?: string };
  x?: number;
  y?: number;
};
type Edge = {
  id: string;
  source_id: string;
  target_id: string;
  action: string;
  timestamp?: string | null;
};
type Cluster = { id: string; account_ids: string[]; density: number };
type Graph = { nodes: Entity[]; edges: Edge[]; hidden_nodes: number; clusters: Cluster[] };
type MatchedEvent = {
  event_id: string;
  account_id: string;
  account_label?: string;
  content_id: string;
  content_label?: string;
  action?: string;
  timestamp: string;
  text?: string;
  text_truncated?: boolean;
  url?: string | null;
  source_post_url?: string;
};
type Episode = {
  time: string | number;
  last_match_time?: string | number;
  strength: number;
  event_ids: string[];
  lexical_similarity: number;
  shared_urls: string[];
  separation_seconds: number;
  matched_events?: MatchedEvent[];
};
type Finding = {
  id: string;
  source_id: string;
  target_id: string;
  strong: boolean;
  score: number;
  episode_count: number;
  baseline_max: number;
  baseline_counts: number[];
  episodes: Episode[];
  evidence_truncated?: boolean;
  contributions?: { mean_signal_strength: number; recurrence_factor: number; excess_fraction: number };
};
type SwarmResult = {
  collection?: CollectionInfo;
  status: "complete" | "needs_review" | "insufficient_data";
  counts: {
    observations: number;
    eligible_events: number;
    accounts: number;
    strong_pairs: number;
    pair_comparisons: number;
  };
  warnings: string[];
  limitations: string[];
  formula: string;
  clusters: Cluster[];
  account_labels?: Record<string, string>;
  parameters: { window_seconds: number; minimum_episodes: number; baseline_trials: number };
  findings: Finding[];
};
type Job = {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
  result: SwarmResult | null;
  error: unknown;
};
type RunContext = { datasetId: string; name: string; provenance: string; revision: number };
type PendingJob = RunContext & { jobId: string };
type Snapshot = PendingJob & { result: SwarmResult; graph: Graph };
type Selection = { kind: "cluster" | "pair" | "entity"; id: string };
type Operation = { controller: AbortController; deadline: number; timedOut: boolean };
type DisplayLink = { id: string; source: string; target: string };
type CollectionInfo = {
  post_count: number;
  accounts_with_posts: number;
  started_at_utc: string;
  oldest_post_utc: string | null;
  newest_post_utc: string | null;
  warnings: string[];
  accounts: { did: string; handle?: string; posts_collected?: number; stop_reason: string; skipped_entries?: Record<string, number> }[];
};
type CollectedPosts = {
  dataset_id: string;
  name: string;
  rows: InputRow[];
  collection: CollectionInfo;
  posts: Record<string, { source_post_url: string; author_handle_at_collection: string }>;
};
type CollectionJob = Omit<Job, "result"> & { result: CollectedPosts | null };

const MAX_BYTES = 10_000_000;
const MAX_EVENTS = 5000;
const OVERALL_TIMEOUT = 11 * 60 * 1000;
const API = "/api/v1";

function errorText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    const lines = value.slice(0, 12).map(errorText);
    if (value.length > 12) lines.push(`…and ${value.length - 12} more errors.`);
    return lines.join("\n");
  }
  if (value && typeof value === "object") {
    const item = value as Record<string, unknown>;
    if (item.detail !== undefined) return errorText(item.detail);
    if (item.msg !== undefined) {
      const location = Array.isArray(item.loc) ? `${item.loc.join(" → ")}: ` : "";
      return location + errorText(item.msg);
    }
    if (item.message !== undefined) return errorText(item.message);
    return JSON.stringify(value);
  }
  return value == null ? "No further details supplied." : String(value);
}

// Every request has its own deadline as well as the operation's abort signal.
async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal, timeout = 30_000): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const response = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      signal: controller.signal,
    });
    const text = await response.text();
    let body: unknown;
    try { body = text ? JSON.parse(text) : null; }
    catch { throw new Error(`API returned an unreadable response (HTTP ${response.status}). Check the backend connection.`); }
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${errorText(body)}`);
    return body as T;
  } catch (error) {
    if (timedOut && !signal?.aborted) throw new Error("Request timed out after 30 seconds. The server may still be working; no automatic retry was made.");
    if (error instanceof TypeError && !controller.signal.aborted) throw new Error("Cannot reach the API. Check the backend connection and try again.");
    throw error;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      reject(new DOMException("Tracking stopped", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}

// Handles quoted commas, escaped quotes, CRLF, and quoted multiline fields.
// CSV is still sent unchanged to the server; this pass only validates the editor.
function csvRows(input: string): InputRow[] {
  const records: string[][] = [];
  let row: string[] = [], field = "", quoted = false, closedQuote = false;
  const finishField = () => { row.push(field); field = ""; closedQuote = false; };
  const finishRow = () => {
    finishField();
    if (row.some((cell) => cell !== "")) records.push(row);
    row = [];
    if (records.length > MAX_EVENTS + 1) throw new Error("Import exceeds 5,000 events.");
  };
  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (quoted) {
      if (char === '"' && input[i + 1] === '"') { field += '"'; i++; }
      else if (char === '"') { quoted = false; closedQuote = true; }
      else field += char;
    } else if (char === ",") finishField();
    else if (char === "\n" || char === "\r") {
      finishRow();
      if (char === "\r" && input[i + 1] === "\n") i++;
    } else if (char === '"' && field === "" && !closedQuote) quoted = true;
    else if (char === '"' || closedQuote) throw new Error("Malformed CSV: check quotes and delimiters.");
    else field += char;
  }
  if (quoted) throw new Error("Malformed CSV: a quoted field is not closed.");
  finishRow();
  const [headers, ...data] = records;
  if (!headers || !data.length) throw new Error("CSV needs a header row and at least one event.");
  if (headers.some((header) => !header) || new Set(headers).size !== headers.length) throw new Error("CSV headers must be nonempty and unique.");
  return data.map((cells, index) => {
    if (cells.length !== headers.length) throw new Error(`CSV row ${index + 1}: expected ${headers.length} fields, received ${cells.length}. Quote text containing commas.`);
    return Object.fromEntries(headers.map((header, i) => [header, cells[i]]));
  });
}

function validateInput(name: string, input: string, format: InputFormat): string {
  if (!name.trim() || name.trim().length > 200) throw new Error("Investigation name must contain 1–200 characters.");
  if (!input.trim()) throw new Error("Load an example, upload a file, or paste event rows first.");
  if (new Blob([input]).size > MAX_BYTES) throw new Error("Input exceeds 10 MB.");
  let rows: unknown;
  if (format === "json") {
    try { rows = JSON.parse(input.replace(/^\uFEFF/, "")); }
    catch (error) { throw new Error(`Invalid JSON: ${errorText(error instanceof Error ? error.message : error)}`); }
  } else rows = csvRows(input.replace(/^\uFEFF/, ""));
  if (!Array.isArray(rows) || !rows.length) throw new Error("Input must contain a nonempty array of event objects.");
  if (rows.length > MAX_EVENTS) throw new Error("Import exceeds 5,000 events.");
  const errors: string[] = [];
  rows.forEach((value, index) => {
    const fail = (message: string) => errors.push(`Row ${index + 1}: ${message}`);
    if (!value || typeof value !== "object" || Array.isArray(value)) { fail("expected an event object."); return; }
    const row = value as InputRow;
    for (const key of ["account_id", "content_id"]) {
      if (typeof row[key] !== "string" || !row[key].trim()) fail(`${key} must be a nonempty string.`);
    }
    if (!["created", "reposted", "replied_to", "liked"].includes(String(row.action))) fail("action must be created, reposted, replied_to, or liked.");
    if (row.timestamp != null && row.timestamp !== "") {
      const timestamp = row.timestamp;
      if (typeof timestamp !== "string" || !/[Tt ].*(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(timestamp) || !Number.isFinite(Date.parse(timestamp))) {
        fail("timestamp must be ISO 8601 with a timezone, e.g. 2026-11-14T09:00:00Z or +00:00.");
      }
    }
    if (row.action === "created" && !(typeof row.text === "string" && row.text.trim()) && !row.url) fail("created content needs text or a URL.");
  });
  if (errors.length) throw new Error(errorText(errors));
  const payload = JSON.stringify(format === "json" ? { name: name.trim(), rows } : { name: name.trim(), csv: input.replace(/^\uFEFF/, "") });
  if (new Blob([payload]).size > MAX_BYTES) throw new Error("Import exceeds 10 MB after JSON encoding. Reduce the input size.");
  return payload;
}

function number(value: number | undefined, digits?: number): string {
  if (value == null || !Number.isFinite(value)) return "Not reported";
  return digits == null ? value.toLocaleString() : value.toFixed(digits);
}

function timestamp(value: string | number | undefined): string {
  if (value == null) return "Not reported";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isFinite(date.getTime()) ? date.toISOString().replace("T", " ").replace(".000Z", " UTC") : String(value);
}

function SourceLink({ url }: { url: string }) {
  let safe = false;
  try { safe = ["http:", "https:"].includes(new URL(url).protocol); } catch { /* Display malformed URLs as text only. */ }
  return safe ? <a href={url} target="_blank" rel="noopener noreferrer">{url}</a> : <span>{url}</span>;
}

function entityLabel(id: string, snapshot: Snapshot): string {
  const node = snapshot.graph.nodes.find((node) => node.id === id);
  return snapshot.result.account_labels?.[id] || (node?.data.handle ? `@${node.data.handle}` : node?.data.source_id) || id;
}

function groupLabel(id: string, snapshot: Snapshot): string {
  const index = snapshot.result.clusters.findIndex((group) => group.id === id);
  return index < 0 ? "Account group" : `Group ${index + 1}`;
}

function activityLabel(action?: string): string {
  return action === "created" ? "Published this post" : action === "reposted" ? "Reposted this post" : action === "replied_to" ? "Replied to this post" : "Recorded activity";
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return <div><dt>{label}</dt><dd>{value}<small>{hint}</small></dd></div>;
}

function ReadingGuide() {
  const terms = [
    ["Account", "Who acted. A person, organization or automated account—we do not determine which."],
    ["Post / content", "The material an account published or interacted with. Identical text can appear in separate posts."],
    ["Recorded action / observation", "One stored relationship: an account published or reposted a post, or a post linked to a URL."],
    ["Usable activity / eligible event", "An action with a usable time and enough text or a valid URL. Usable does not mean suspicious. Likes and derived URL links are excluded."],
    ["Matching occasion / episode", "One burst of matching activity between two accounts. Another occasion begins after more than the matching window without a match."],
    ["Group / cluster", "At least three accounts, with a flagged connection between every pair. These are two names for the same thing."],
    ["Shuffled comparison / baseline", "The detector scrambles posting times and counts matches again. This is a rough comparison, not a significance test."],
    ["Coordination score", "A 0–1 heuristic combining recurrence, match strength and excess over shuffled timing. It is not a bot probability."],
  ];
  return <details className="swarm-reading-guide">
    <summary><span>New here? Understand what you’re looking at</span><span className="swarm-muted">A quick guide to the words and numbers</span></summary>
    <div className="swarm-glossary">{terms.map(([term, meaning]) => <div key={term}><h4>{term}</h4><p>{meaning}</p></div>)}</div>
    <p className="swarm-guide-note">We look for repeated similar wording or shared URLs close together in time. Scheduled campaigns, news sharing and legitimate organizations can also match. No AI provider or bot classifier is used here.</p>
  </details>;
}

function InputPreview({ input, format, collected }: { input: string; format: InputFormat; collected?: CollectedPosts | null }) {
  const preview = useMemo(() => {
    if (!input.trim() || new Blob([input]).size > MAX_BYTES) return null;
    try {
      const parsed: unknown = format === "json" ? JSON.parse(input.replace(/^\uFEFF/, "")) : csvRows(input.replace(/^\uFEFF/, ""));
      if (!Array.isArray(parsed) || !parsed.length || parsed.some((row) => !row || typeof row !== "object" || Array.isArray(row))) return null;
      const rows = parsed as InputRow[];
      const accounts = new Set(rows.filter((row) => typeof row.account_id === "string").map((row) => JSON.stringify([row.platform || "unknown", row.account_id])));
      return { rows, accounts: accounts.size };
    } catch { return null; }
  }, [input, format]);
  if (!preview) return null;
  return <div className="swarm-input-preview">
    <div className="swarm-preview-heading"><strong>{collected ? "Real Bluesky posts loaded" : "Activity loaded"}</strong><span>{number(preview.rows.length)} rows · {number(preview.accounts)} accounts</span></div>
    <p className="swarm-muted">{collected ? "Original post previews—not detected bots. Times are UTC. Open the sources to verify." : `A preview of the first ${Math.min(3, preview.rows.length)} rows. Full validation happens when you analyze.`}</p>
    {preview.rows.slice(0, 3).map((row, index) => {
      const source = collected?.posts[String(row.content_id)];
      return <div className="swarm-preview-row" key={index}>
      <strong>{source?.author_handle_at_collection ? `@${source.author_handle_at_collection}` : String(row.account_id || "Account not supplied")}</strong><span>{row.timestamp ? timestamp(String(row.timestamp)) : "Time not supplied"}</span>
      <p>{String(row.text || row.url || "No post text supplied").slice(0, 150)}</p>
      {source && <a className="swarm-source-post" href={source.source_post_url} target="_blank" rel="noopener noreferrer">Open original on Bluesky ↗</a>}
    </div>; })}
  </div>;
}

function CollectionCoverage({ collection, datasetId }: { collection: CollectionInfo; datasetId: string }) {
  return <details className="swarm-collection-coverage">
    <summary>Bluesky collection coverage · {number(collection.post_count)} posts · {number(collection.accounts_with_posts)} accounts</summary>
    <p>These are multiple posts per selected account—not newly discovered accounts. Feed caps can omit activity; no topic search or repost chains were collected.</p>
    <p className="swarm-muted">Collected {timestamp(collection.started_at_utc)}. Posting dates: {timestamp(collection.oldest_post_utc || undefined)} → {timestamp(collection.newest_post_utc || undefined)}.</p>
    <ul>{collection.accounts.map((account, index) => <li key={`${account.did}-${index}`}><strong>@{account.handle || account.did}</strong>: {number(account.posts_collected || 0)} authored posts · {account.stop_reason.replaceAll("_", " ")}{account.skipped_entries?.repost_not_collected ? ` · ${account.skipped_entries.repost_not_collected} repost wrappers skipped` : ""}</li>)}</ul>
    <ul>{collection.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
    <a href={`${API}/datasets/${encodeURIComponent(datasetId)}/provenance`} target="_blank" rel="noopener noreferrer">View saved original records &amp; source provenance ↗</a>
  </details>;
}

function BlueskyImport({ disabled, onLoad, onBusyChange }: { disabled: boolean; onLoad: (value: CollectedPosts) => void; onBusyChange: (value: boolean) => void }) {
  const [profiles, setProfiles] = useState("");
  const [limit, setLimit] = useState(50);
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState("");
  const [message, setMessage] = useState("Paste profiles you want to compare. Nothing is fetched until you click below.");
  const [error, setError] = useState("");
  const controllerRef = useRef<AbortController | null>(null);
  const jobRef = useRef("");

  useEffect(() => () => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    if (jobRef.current) void request(`/jobs/${encodeURIComponent(jobRef.current)}/cancel`, { method: "POST", keepalive: true }).catch(() => undefined);
  }, []);

  async function track(job: CollectionJob, signal: AbortSignal) {
    while (job.status === "queued" || job.status === "running") {
      setMessage(job.status === "queued" ? "Collection queued. Waiting for a worker…" : "Fetching selected public author feeds from Bluesky. Reposts are skipped…");
      await pause(1500, signal);
      job = await request<CollectionJob>(`/jobs/${encodeURIComponent(job.id)}`, {}, signal);
    }
    if (signal.aborted) return;
    jobRef.current = ""; setJobId("");
    if (job.status === "cancelled") { setMessage("Collection cancelled. Your previous input and result are unchanged."); return; }
    if (job.status !== "completed") throw new Error(`Collection ${job.status}: ${errorText(job.error)}`);
    const value = job.result;
    if (!value?.dataset_id || !value.name || !Array.isArray(value.rows) || !value.rows.length || !value.collection || !value.posts) throw new Error("Collection returned an incomplete snapshot. Previous input and result are unchanged.");
    if (signal.aborted) return;
    onLoad(value);
    setMessage(`Fetched ${number(value.rows.length)} real authored posts from ${number(value.collection.accounts_with_posts)} accounts. Review the post previews, then click Analyze activity.`);
  }

  async function run(resume = false) {
    let actors: string[] = [];
    if (!resume) {
      try { actors = parseBlueskyProfiles(profiles); }
      catch (failure) { setError(failure instanceof Error ? failure.message : errorText(failure)); return; }
      if (!actors.length) { setError("Enter between 1 and 10 public Bluesky profiles or handles, separated by newlines."); return; }
    }
    const controller = new AbortController(); controllerRef.current = controller;
    setBusy(true); onBusyChange(true); setError("");
    const deadline = window.setTimeout(() => controller.abort(), OVERALL_TIMEOUT);
    try {
      setMessage(resume ? "Checking the saved collection job…" : "Requesting a bounded public collection…");
      const job = resume
        ? await request<CollectionJob>(`/jobs/${encodeURIComponent(jobRef.current)}`, {}, controller.signal)
        : await request<CollectionJob>("/bluesky/collect", { method: "POST", body: JSON.stringify({ actors, per_actor: limit }) }, controller.signal);
      if (!job?.id) throw new Error("Collection returned no job reference. No automatic retry was made.");
      jobRef.current = job.id; setJobId(job.id);
      await track(job, controller.signal);
    } catch (failure) {
      if (controllerRef.current !== controller) return;
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : errorText(failure));
      else setError("Tracking stopped. If a job reference is shown, resume tracking or cancel it; no automatic retry was made.");
    } finally {
      window.clearTimeout(deadline);
      if (controllerRef.current === controller) { controllerRef.current = null; setBusy(false); onBusyChange(false); }
    }
  }

  async function cancelCollection() {
    if (!jobRef.current) return;
    const id = jobRef.current;
    controllerRef.current?.abort();
    // Keep parent inputs locked until server-side cancellation is confirmed.
    const controller = new AbortController(); controllerRef.current = controller;
    setBusy(true); onBusyChange(true); setError("");
    setMessage("Stopping collection. A public request already in flight may take up to 25 seconds to stop…");
    try {
      const job = await request<CollectionJob>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }, controller.signal);
      await track(job, controller.signal);
    } catch (failure) { setError(failure instanceof Error ? failure.message : errorText(failure)); }
    finally { if (controllerRef.current === controller) { controllerRef.current = null; setBusy(false); onBusyChange(false); } }
  }

  return <details className="swarm-bluesky-import">
    <summary>Import real posts from Bluesky ↗</summary>
    <p>Choose public profiles, fetch their latest authored posts, then use the same analysis and evidence view below. No separate experiment page.</p>
    <label className="swarm-field" htmlFor="swarm-bluesky-profiles">BLUESKY PROFILE URLS OR HANDLES</label>
    <textarea id="swarm-bluesky-profiles" value={profiles} disabled={disabled || busy || !!jobId} rows={3} maxLength={4000} spellCheck={false} placeholder={"https://bsky.app/profile/bsky.app\natproto.com"} onChange={(event) => setProfiles(event.target.value)} aria-describedby="swarm-bluesky-help" />
    <p id="swarm-bluesky-help" className="swarm-muted">One per line, up to 10. Use profile URLs or @handles—not post links, article URLs or keywords. Choose at least two accounts for comparison.</p>
    <label className="swarm-field" htmlFor="swarm-bluesky-limit">MAXIMUM POSTS PER ACCOUNT</label>
    <select id="swarm-bluesky-limit" value={limit} disabled={disabled || busy || !!jobId} onChange={(event) => setLimit(Number(event.target.value))}>{[10, 50, 100, 200].map((value) => <option key={value} value={value}>{value} posts per account</option>)}</select>
    <p className="swarm-muted">At most three feed pages per account. Public posts only; no login or LLM calls. This does not discover accounts, search topics or collect repost chains. Original records are stored on this server.</p>
    <button type="button" className="swarm-fetch" disabled={disabled || busy || !!jobId || !profiles.trim()} onClick={() => void run()}>{busy ? "Fetching public posts…" : "Fetch public posts →"}</button>
    <p className="swarm-collection-status" role="status" aria-live="polite">{message}</p>
    {jobId && <div className="swarm-actions"><button type="button" onClick={() => void cancelCollection()}>Cancel collection</button>{!busy && <button type="button" disabled={disabled} onClick={() => void run(true)}>Resume collection tracking</button>}</div>}
    {error && <div className="swarm-error" role="alert"><strong>Bluesky collection did not finish</strong><p>{error}</p></div>}
  </details>;
}

function defaultSelection(snapshot: Snapshot): Selection | null {
  const group = snapshot.result.clusters[0];
  if (group) return { kind: "cluster", id: group.id };
  const pair = snapshot.result.findings.find((finding) => finding.strong) || snapshot.result.findings[0];
  if (pair) return { kind: "pair", id: pair.id };
  const entity = snapshot.graph.nodes.find((node) => node.kind === "account") || snapshot.graph.nodes[0];
  return entity ? { kind: "entity", id: entity.id } : null;
}

function FindingEvidence({ finding, snapshot }: { finding: Finding; snapshot: Snapshot }) {
  const { result } = snapshot;
  const strength = finding.contributions?.mean_signal_strength;
  const recurrence = finding.contributions?.recurrence_factor ?? Math.min(1, finding.episode_count / result.parameters.minimum_episodes);
  const maxCount = Math.max(1, finding.episode_count, finding.baseline_max);
  return (
    <article className="swarm-pair-evidence">
      <h4>{entityLabel(finding.source_id, snapshot)} <span>↔</span> {entityLabel(finding.target_id, snapshot)}</h4>
      <p className={`swarm-evidence-badge ${finding.strong ? "is-flagged" : ""}`}>{finding.strong ? "Repeated coordination signal" : "Candidate only · below the strong-connection rules"}</p>
      <p className="swarm-pair-story">These accounts matched on <strong>{number(finding.episode_count)} separate occasions</strong>. A match means similar wording or a shared URL within {number(result.parameters.window_seconds)} seconds—not necessarily an identical post.</p>
      <dl className="swarm-metrics">
        <Metric label="Coordination score" value={`${number(finding.score, 3)} / 1`} hint="A heuristic, not a bot probability" />
        <Metric label="Matching occasions" value={number(finding.episode_count)} hint="Separate bursts, called episodes" />
        <Metric label="Largest shuffled count" value={number(finding.baseline_max)} hint="Most occasions after scrambling times" />
      </dl>
      <div className="swarm-baseline-comparison" aria-label={`${finding.episode_count} real occasions compared with a maximum of ${finding.baseline_max} in shuffled timing runs`}>
        <div><span>Actual timing</span><strong>{number(finding.episode_count)} occasions</strong><i style={{ width: `${finding.episode_count / maxCount * 100}%` }} /></div>
        <div><span>Most in shuffled runs</span><strong>{number(finding.baseline_max)} occasions</strong><i style={{ width: `${finding.baseline_max / maxCount * 100}%` }} /></div>
      </div>
      <details className="swarm-score-explainer">
        <summary>Why is the score {number(finding.score, 3)}?</summary>
        <p>We combine how often the pair matches, how strong those matches are, and how much recurrence exceeds the largest shuffled count.</p>
        <p className="swarm-formula">Score = min(1, N / M) × S × max(0, N − B) / N</p>
        <dl className="swarm-score-variables">
          <div><dt>N · actual occasions</dt><dd>{number(finding.episode_count)}</dd></div>
          <div><dt>M · minimum required</dt><dd>{number(result.parameters.minimum_episodes)}</dd></div>
          <div><dt>S · average match strength</dt><dd>{number(strength, 3)}</dd></div>
          <div><dt>B · largest shuffled count</dt><dd>{number(finding.baseline_max)}</dd></div>
        </dl>
        {strength != null && <p className="swarm-formula">{number(recurrence, 3)} × {number(strength, 3)} × max(0, {finding.episode_count} − {finding.baseline_max}) / {finding.episode_count} = {number(finding.score, 3)} <span className="swarm-muted">(rounded)</span></p>}
        <p>Each occasion uses its strongest text or shared-URL match. Identical normalized word sets score 1 for text; widely shared URLs are discounted. The time gap qualifies a match but is not directly multiplied into this score.</p>
        <p>Shuffled counts: {finding.baseline_counts?.length ? finding.baseline_counts.join(", ") : "No completed shuffled runs"}.</p>
        {finding.baseline_counts.length < result.parameters.baseline_trials && <p className="swarm-notice">Only {finding.baseline_counts.length} of {result.parameters.baseline_trials} shuffled runs completed. Treat this as incomplete evidence.</p>}
        <p className="swarm-muted">The score is not a percentage chance of being a bot. These shuffled runs are not a statistical significance test; real-world accuracy has not been measured.</p>
      </details>
      <div className="swarm-occasion-heading"><h4>Compare the matching activity</h4><p>Each occasion is one burst, not one post. Below are the strongest two supporting actions from each burst.</p></div>
      {(finding.evidence_truncated || finding.episode_count > finding.episodes.length) && <p className="swarm-notice">Showing {finding.episodes.length} of {finding.episode_count} occasions. The score uses all counted occasions.</p>}
      <div className="swarm-episodes">
        {finding.episodes.map((episode, index) => (
          <details className="swarm-episode" key={`${episode.time}-${index}`} open={index === 0}>
            <summary><span className="swarm-occasion-number">{String(index + 1).padStart(2, "0")}</span><span><strong>Matching occasion {index + 1}</strong><time>First match {timestamp(episode.time)}</time></span><span className="swarm-time-gap">{number(episode.separation_seconds, 2)} s apart</span></summary>
            <div className="swarm-match-tags"><span>{episode.lexical_similarity === 1 ? "Same normalized words" : episode.lexical_similarity >= 0.85 ? "Very similar wording" : "Shared URL match"}</span><span className="swarm-mobile-gap">{number(episode.separation_seconds, 2)} seconds apart</span>{episode.shared_urls?.length > 0 && <span>{episode.shared_urls.length} shared {episode.shared_urls.length === 1 ? "URL" : "URLs"}</span>}</div>
            <div className="swarm-post-comparison">{episode.matched_events?.length ? episode.matched_events.map((event, eventIndex) => {
              const preview = (event.text || "").slice(0, 1200);
              const truncated = event.text_truncated || (event.text?.length || 0) > preview.length;
              return (
                <div className="swarm-matched-event" key={`${event.event_id}-${eventIndex}`}>
                  <span className="swarm-post-action">{activityLabel(event.action)}</span>
                  <strong>{event.account_label || entityLabel(event.account_id, snapshot)}</strong>
                  <time>{timestamp(event.timestamp)}</time>
                  <p>{preview || "No text supplied for this event."}</p>
                  {event.action === "replied_to" && <p className="swarm-muted">This is the referenced post, not the reply’s own text.</p>}
                  {truncated && <p className="swarm-notice">Text preview truncated.</p>}
                  {event.source_post_url && <p className="swarm-original-link">Original Bluesky post: <SourceLink url={event.source_post_url} /></p>}
                  {event.url && <SourceLink url={event.url} />}
                  <details><summary>Post &amp; source identifiers</summary><p>Post: {event.content_label || event.content_id}</p><p>Internal content ID: {event.content_id}</p><p>Action ID: {event.event_id}</p></details>
                </div>
              );
            }) : <p className="swarm-notice">This detector response did not supply matched-event text previews.</p>}</div>
            <details className="swarm-occasion-technical"><summary>Technical details for this occasion</summary>
              <dl className="swarm-metrics">
                <Metric label="Word-set similarity" value={number(episode.lexical_similarity, 3)} hint="Jaccard overlap; not meaning or truthfulness" />
                <Metric label="Time between actions" value={`${number(episode.separation_seconds, 2)} s`} hint={`Must be within ${result.parameters.window_seconds} seconds`} />
                <Metric label="Match strength" value={number(episode.strength, 3)} hint="Strongest text or URL signal in this burst" />
              </dl>
              {episode.last_match_time != null && <p>Last matching activity in this burst: {timestamp(episode.last_match_time)}</p>}
              {episode.shared_urls?.length ? <><p>Shared URLs</p><ul>{episode.shared_urls.map((url) => <li key={url}><SourceLink url={url} /></li>)}</ul></> : <p>No shared URLs in this representative match.</p>}
              <p>Supporting action IDs</p><ul>{episode.event_ids?.map((id) => <li key={id}>{id}</li>)}</ul>
            </details>
          </details>
        ))}
      </div>
    </article>
  );
}

function EvidenceInspector({ snapshot, selection, select }: { snapshot: Snapshot; selection: Selection | null; select: (selection: Selection) => void }) {
  const [pairId, setPairId] = useState("");
  const node = selection?.kind === "entity" ? snapshot.graph.nodes.find((entry) => entry.id === selection.id) : undefined;
  const cluster = selection?.kind === "cluster" ? snapshot.result.clusters.find((entry) => entry.id === selection.id) : undefined;
  const related = snapshot.result.findings.filter((finding) => {
    if (!selection) return false;
    if (selection.kind === "pair") return finding.id === selection.id;
    if (cluster) return cluster.account_ids.includes(finding.source_id) && cluster.account_ids.includes(finding.target_id);
    if (selection.kind === "entity") {
      return finding.source_id === selection.id || finding.target_id === selection.id || finding.episodes.some((episode) =>
        episode.matched_events?.some((event) => event.content_id === selection.id || event.content_id === node?.data.source_id));
    }
    return false;
  }).sort((a, b) => Number(b.strong) - Number(a.strong) || b.score - a.score);
  const pair = related.find((finding) => finding.id === pairId) || related[0];
  const heading = cluster ? groupLabel(cluster.id, snapshot) : selection?.kind === "entity" ? entityLabel(selection.id, snapshot) : "Two-account comparison";
  return (
    <aside className="swarm-panel swarm-inspection" aria-label="Swarm evidence inspector">
      <header className="swarm-panel-heading">THE EVIDENCE / {cluster ? "ACCOUNT GROUP" : selection?.kind === "entity" ? "SELECTED ITEM" : "ACCOUNT PAIR"}</header>
      <div className="swarm-panel-body">
        {!selection ? <p className="swarm-muted">Select an entity, group, or pair to inspect evidence.</p> : <>
          <h3>{heading}</h3>
          {cluster && <>
            <p><strong>{cluster.account_ids.length} accounts</strong> with a flagged connection between every pair. A group is also called a cluster; it is not proof of shared ownership or automation.</p>
            <div className="swarm-members">{cluster.account_ids.map((id) => <button type="button" key={id} onClick={() => select({ kind: "entity", id })}>{entityLabel(id, snapshot)}</button>)}</div>
            <p className="swarm-muted">Select a name to inspect that account, or compare a pair below.</p>
          </>}
          {selection.kind === "entity" && <>
            <p className="swarm-kicker">{node?.kind === "content" ? "Post / content" : "Account"}{node?.data.platform ? ` / ${node.data.platform}` : ""}</p>
            <p className="swarm-muted">{node?.kind === "content" ? "This is one post, not an account. Identical wording can appear in other posts." : "This is an account that performed recorded actions. Its name is not evidence that it is a bot."}</p>
            {!node && <p className="swarm-notice">This account is outside the displayed graph. The map includes only attributed agents with publishing or editing activity or declared capability; at most 300 entities are drawn.</p>}
            {node?.data.text && <div className="swarm-entity-text"><p>{node.data.text.slice(0, 1200)}</p>{node.data.text.length > 1200 && <p className="swarm-notice">Text preview truncated.</p>}</div>}
            {node?.data.url && <p><SourceLink url={node.data.url} /></p>}
            {node?.data.source_post_url && <p className="swarm-original-link">Open original on Bluesky: <SourceLink url={node.data.source_post_url} /></p>}
          </>}
          {related.length > 1 && <label className="swarm-field">COMPARE TWO ACCOUNTS / {related.length} PAIRS
            <select value={pair?.id || ""} onChange={(event) => setPairId(event.target.value)}>{related.map((finding) => <option key={finding.id} value={finding.id}>{entityLabel(finding.source_id, snapshot)} ↔ {entityLabel(finding.target_id, snapshot)}{finding.strong ? " · strong" : " · candidate"}</option>)}</select>
          </label>}
          {pair ? <FindingEvidence key={pair.id} finding={pair} snapshot={snapshot} /> : <p className="swarm-muted">No pair-level coordination evidence was returned for this selection. This is not a safety verdict.</p>}
        </>}
      </div>
    </aside>
  );
}

function ObservationGraph({ snapshot, selection, select }: { snapshot: Snapshot; selection: Selection | null; select: (selection: Selection) => void }) {
  const graphRef = useRef<ForceGraphMethods<Entity, DisplayLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const fitted = useRef(false);
  const graph = useMemo(() => {
    const contents = new Set(snapshot.graph.nodes.filter((node) => node.kind === "content").map((node) => node.id));
    const accounts = new Set(snapshot.graph.nodes.filter((node) => node.kind === "account").map((node) => node.id));
    // Relationships come from the observed graph; detector findings stay in the evidence panels.
    const links: DisplayLink[] = snapshot.graph.edges
      .filter((edge) => accounts.has(edge.source_id) && contents.has(edge.target_id))
      .map((edge) => ({ id: edge.id, source: edge.source_id, target: edge.target_id }));
    // d3-force mutates positions and link endpoints. Never hand it the API snapshot.
    return { nodes: snapshot.graph.nodes.map((node) => ({ ...node, data: { ...node.data } })), links };
  }, [snapshot]);
  const highlighted = useMemo(() => {
    if (selection?.kind === "cluster") return new Set(snapshot.result.clusters.find((cluster) => cluster.id === selection.id)?.account_ids || []);
    if (selection?.kind === "pair") {
      const pair = snapshot.result.findings.find((finding) => finding.id === selection.id);
      return new Set(pair ? [pair.source_id, pair.target_id] : []);
    }
    return new Set(selection ? [selection.id] : []);
  }, [snapshot, selection]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.floor(entry.contentRect.width), height = Math.floor(entry.contentRect.height);
      setSize((previous) => previous.width === width && previous.height === height ? previous : { width, height });
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const frame = requestAnimationFrame(() => graphRef.current?.zoomToFit(0, 36));
    return () => cancelAnimationFrame(frame);
  }, [size]);

  function drawNode(node: Entity, context: CanvasRenderingContext2D, scale: number) {
    const x = node.x ?? 0, y = node.y ?? 0;
    const radius = node.kind === "account" ? 4.5 : 3.5;
    context.fillStyle = node.kind === "account" ? "#a2927f" : "#f4efe6";
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
    if (highlighted.has(node.id)) {
      context.strokeStyle = "#e34e48";
      context.lineWidth = 1.5 / scale;
      context.beginPath(); context.arc(x, y, radius + 3, 0, Math.PI * 2); context.stroke();
    }
    if (highlighted.has(node.id) || (scale > 1.3 && node.kind === "account")) {
      const label = entityLabel(node.id, snapshot);
      context.font = `${11 / scale}px monospace`;
      context.fillStyle = "#f4efe6";
      context.fillText(label.length > 30 ? `${label.slice(0, 29)}…` : label, x + radius + 5, y + 3 / scale);
    }
  }
  function zoom(factor: number) {
    const instance = graphRef.current;
    if (instance) instance.zoom(Math.max(0.05, Math.min(20, instance.zoom() * factor)), 200);
  }
  return (
    <section className="swarm-panel" id="swarm-map" aria-label="Observed network graph">
      <header className="swarm-panel-heading"><span>NETWORK MAP / WHO ACTED ON WHAT</span><span>{graph.nodes.length} items · {graph.links.length} observed actions</span></header>
      <p className="swarm-map-explainer">Agents connect to posts through observed actions, including replies recorded in post metadata. Agents need attributed publishing or editing activity or declared capability. URLs appear in post details; coordination findings remain in the evidence panels and may cover accounts outside this map.</p>
      {snapshot.graph.hidden_nodes > 0 && <p className="swarm-notice swarm-graph-warning" role="note">Graph truncated: {number(snapshot.graph.hidden_nodes)} entities hidden; at most 300 are drawn. Counts and evidence below cover the full detector result, not just this view.</p>}
      <div className="swarm-canvas" ref={containerRef}>
        {size.width > 0 && size.height > 0 && <ForceGraph2D<Entity, DisplayLink>
          ref={graphRef}
          graphData={graph}
          width={size.width}
          height={size.height}
          backgroundColor="#141414"
          cooldownTicks={100}
          minZoom={0.05}
          maxZoom={20}
          nodeCanvasObject={drawNode}
          nodeLabel={() => ""}
          onNodeClick={(node) => select({ kind: "entity", id: node.id })}
          linkColor={() => "#60584e"}
          linkWidth={0.8}
          enableZoomInteraction={(event) => event.type !== "wheel" || event.ctrlKey || event.metaKey}
          onEngineStop={() => { if (!fitted.current) { fitted.current = true; graphRef.current?.zoomToFit(250, 36); } }}
        />}
        {!graph.nodes.length && <p className="swarm-canvas-empty">No entities returned for this graph.</p>}
      </div>
      <div className="swarm-graph-footer">
        <div className="swarm-zoom" aria-label="Graph zoom controls">
          <button type="button" onClick={() => zoom(1.3)} aria-label="Zoom in">+</button>
          <button type="button" onClick={() => zoom(1 / 1.3)} aria-label="Zoom out">−</button>
          <button type="button" onClick={() => graphRef.current?.zoomToFit(200, 36)}>Fit</button>
        </div>
        <div className="swarm-legend" aria-label="Graph legend"><span><i className="swarm-account-key" />agent</span><span><i className="swarm-content-key" />post</span><span><i className="swarm-observed-key" />observed action</span></div>
      </div>
      <p className="swarm-graph-hint">Drag to pan · use + / − or Ctrl/⌘ + scroll to zoom · select an entity below without using the canvas.</p>
    </section>
  );
}

function ResultSummary({ snapshot, exportResult }: { snapshot: Snapshot; exportResult: () => void }) {
  const { result } = snapshot;
  const takeaway = result.status === "insufficient_data" ? "There isn’t enough usable activity to draw a conclusion."
    : result.status === "needs_review" ? "Read this result with caution. Some evidence has limits."
    : result.clusters.length > 0 ? `${result.clusters.length} account ${result.clusters.length === 1 ? "group is" : "groups are"} worth a closer look.`
    : result.counts.strong_pairs > 0 ? "Repeated matches found between account pairs."
    : "No strong repeating pattern found in this sample.";
  const statusText = result.status === "insufficient_data"
    ? "Insufficient data — the detector cannot draw a coordination conclusion from this input."
    : result.status === "needs_review"
      ? "Needs review — this result has limitations or incomplete coverage. Do not treat it as an exhaustive finding."
      : result.counts.strong_pairs > 0
        ? "Complete — strong coordination signals found. Inspect the episodes and baseline before interpreting them."
        : "Complete — no strong account pairs found under these detector settings.";
  return (
    <section className="swarm-panel swarm-result-summary" aria-label="Detector result">
      <header className="swarm-panel-heading"><span>2 / YOUR RESULT</span><button type="button" onClick={exportResult}>Export result JSON ↓</button></header>
      <div className="swarm-panel-body">
        <h3>{snapshot.name}</h3>
        <p className="swarm-kicker">{snapshot.provenance} · {result.status.replaceAll("_", " ").toUpperCase()}</p>
        <p className="swarm-takeaway">{takeaway}</p>
        <p>{statusText}</p>
        <dl className="swarm-metrics swarm-counts">
          <Metric label="Accounts analyzed" value={number(result.counts.accounts)} hint="Accounts with usable timed activity" />
          <Metric label="Usable activity" value={number(result.counts.eligible_events)} hint="Eligible events—not suspicious events" />
          <Metric label="Flagged account pairs" value={number(result.counts.strong_pairs)} hint="Connections to investigate, not confirmed bots" />
          <Metric label="Groups to review" value={number(result.clusters.length)} hint="3+ mutually connected accounts per group" />
        </dl>
        <p className="swarm-trust-note">Coordination is not proof of bots or malicious intent. {!result.clusters.length && "No strong groups does not prove safety or independence. A strong pair need not form a group."}</p>
        {result.collection && <CollectionCoverage collection={result.collection} datasetId={snapshot.datasetId} />}
        {!!result.warnings?.length && <div className="swarm-notice"><h4>Detector warnings</h4><ul>{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
        {result.status === "insufficient_data" ? <div className="swarm-next-step"><strong>What to do next</strong><p>Add timezone-aware timestamps and repeated activity from at least two accounts. The default settings need three usable events per account and an observation span longer than two minutes.</p></div>
          : <div className="swarm-next-step"><strong>What to do next</strong><p>{result.findings.length ? "Choose a group or account pair below. Compare the actual posts and times before interpreting the score." : "Try a wider sample or a longer time period. This only tests the imported activity under the current matching rules."}</p><div className="swarm-result-links">{result.findings.length > 0 && <a href="#swarm-evidence">Review the matching activity ↓</a>}<a href="#swarm-map">Explore the network map ↓</a></div></div>}
        <details className="swarm-coverage"><summary>What was analyzed? Data coverage &amp; counts</summary>
          <dl className="swarm-score-variables">
            <div><dt>Recorded actions (observations)</dt><dd>{number(result.counts.observations)}</dd></div>
            <div><dt>Usable actions (eligible events)</dt><dd>{number(result.counts.eligible_events)}</dd></div>
            <div><dt>Excluded from timing analysis</dt><dd>{number(Math.max(0, result.counts.observations - result.counts.eligible_events))}</dd></div>
            <div><dt>Candidate comparisons, including shuffles</dt><dd>{number(result.counts.pair_comparisons)}</dd></div>
          </dl>
          <p>An observation records an action or relationship. A post with a URL may create both an account-to-post action and a post-to-URL link, so this is not necessarily a count of posts.</p>
          <p>Usable activity needs a recorded time, referenced content and at least four distinct words or a valid URL. Created, reposted and replied-to actions can qualify; likes and derived URL links do not. Missing or invalid data can also exclude an action.</p>
        </details>
        <details className="swarm-method"><summary>Method, parameters &amp; limitations</summary>
          <p>Window: {number(result.parameters.window_seconds)} s · minimum episodes: {number(result.parameters.minimum_episodes)} · baseline trials: {number(result.parameters.baseline_trials)}</p>
          <p className="swarm-formula">{result.formula}</p>
          <ul>{result.limitations?.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
        </details>
      </div>
    </section>
  );
}

export default function SwarmNetwork() {
  const [examples, setExamples] = useState<Example[]>([]);
  const [examplesError, setExamplesError] = useState("");
  const [loadingExamples, setLoadingExamples] = useState(true);
  const [examplesAttempt, setExamplesAttempt] = useState(0);
  const [exampleId, setExampleId] = useState("");
  const [exampleSource, setExampleSource] = useState<Example | null>(null);
  const [exampleEdited, setExampleEdited] = useState(false);
  const [name, setName] = useState("Untitled investigation");
  const [input, setInput] = useState("");
  const [format, setFormat] = useState<InputFormat>("json");
  const [revision, setRevision] = useState(0);
  const [reading, setReading] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collected, setCollected] = useState<CollectedPosts | null>(null);
  const [busy, setBusy] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [phase, setPhase] = useState<"idle" | "importing" | "analyzing" | "loading">("idle");
  const [activity, setActivity] = useState("Start with a demo, upload a file, or paste your activity below.");
  const [error, setError] = useState("");
  const [pending, setPending] = useState<PendingJob | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const operationRef = useRef<Operation | null>(null);
  const pendingRef = useRef<PendingJob | null>(null);
  const fileReaderRef = useRef<FileReader | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingExamples(true); setExamplesError("");
    request<Example[]>("/swarm/examples", {}, controller.signal).then((items) => {
      if (!Array.isArray(items) || items.some((item) => !item || typeof item.id !== "string" || typeof item.name !== "string" || item.synthetic !== true || !Array.isArray(item.rows))) throw new Error("The examples endpoint returned an unexpected format.");
      if (!controller.signal.aborted) setExamples(items);
    }).catch((failure) => {
      if (!controller.signal.aborted) setExamplesError(`Examples unavailable: ${failure instanceof Error ? failure.message : errorText(failure)} You can still upload or paste input.`);
    }).finally(() => { if (!controller.signal.aborted) setLoadingExamples(false); });
    return () => controller.abort();
  }, [examplesAttempt]);

  useEffect(() => () => {
    const operation = operationRef.current;
    operationRef.current = null;
    operation?.controller.abort();
    if (operation) window.clearTimeout(operation.deadline);
    fileReaderRef.current?.abort();
    // Stop the CPU job as well as local polling when this screen is unmounted.
    const job = pendingRef.current;
    if (job) void request(`/jobs/${encodeURIComponent(job.jobId)}/cancel`, { method: "POST", keepalive: true }).catch(() => undefined);
  }, []);

  function updatePending(value: PendingJob | null) { pendingRef.current = value; setPending(value); }

  async function operate(work: (operation: Operation) => Promise<void>) {
    const previous = operationRef.current;
    previous?.controller.abort();
    if (previous) window.clearTimeout(previous.deadline);
    const operation: Operation = { controller: new AbortController(), deadline: 0, timedOut: false };
    operation.deadline = window.setTimeout(() => { operation.timedOut = true; operation.controller.abort(); }, OVERALL_TIMEOUT);
    operationRef.current = operation;
    setBusy(true); setError("");
    try { await work(operation); }
    catch (failure) {
      if (operationRef.current !== operation) return;
      setError(operation.timedOut ? "Tracking stopped after 11 minutes. The server job may still be running. Resume tracking or cancel it below." : failure instanceof Error ? failure.message : errorText(failure));
      setActivity(pendingRef.current ? "Tracking stopped. Server job status is unconfirmed; no automatic retries." : "Stopped. No new graph was published.");
    } finally {
      window.clearTimeout(operation.deadline);
      if (operationRef.current === operation) { operationRef.current = null; setBusy(false); setPhase("idle"); }
    }
  }

  async function publish(job: Job, context: PendingJob, operation: Operation) {
    const result = job.result;
    if (!result || !["complete", "needs_review", "insufficient_data"].includes(result.status) || !result.counts || !Array.isArray(result.findings) || !Array.isArray(result.clusters) || !result.parameters) throw new Error("Job finished without a supported detector result. The previous graph has been preserved.");
    setPhase("loading");
    setActivity("Patterns checked. Preparing the evidence and network map…");
    const graph = await request<Graph>(`/datasets/${encodeURIComponent(context.datasetId)}/graph?limit=300`, {}, operation.controller.signal);
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges) || typeof graph.hidden_nodes !== "number") throw new Error("The graph response was incomplete. The previous result has been preserved.");
    if (operationRef.current !== operation || operation.controller.signal.aborted) return;
    const next = { ...context, result, graph };
    setSnapshot(next); setSelection(defaultSelection(next));
    setActivity(`Finished: ${result.status.replaceAll("_", " ")}. Showing ${context.name}.`);
  }

  async function track(job: Job, context: PendingJob, operation: Operation) {
    while (job.status === "queued" || job.status === "running") {
      setActivity(job.status === "queued" ? "Your analysis is queued. It will start when a worker is available." : "Looking for repeated wording, shared links and timing patterns…");
      await pause(1500, operation.controller.signal);
      job = await request<Job>(`/jobs/${encodeURIComponent(context.jobId)}`, {}, operation.controller.signal);
      if (operationRef.current !== operation) return;
    }
    updatePending(null);
    if (job.status === "completed") await publish(job, context, operation);
    else if (job.status === "cancelled") setActivity("Job cancelled. No new result was published.");
    else if (job.status === "failed" || job.status === "interrupted") throw new Error(`Detector ${job.status}: ${errorText(job.error)}`);
    else throw new Error(`Unexpected job status: ${String(job.status)}. Tracking stopped.`);
  }

  function start() {
    let payload: string;
    try { payload = validateInput(name, input, format); }
    catch (failure) { setError(failure instanceof Error ? failure.message : errorText(failure)); return; }
    void operate(async (operation) => {
      const signal = operation.controller.signal;
      const useCollected = collected && name === collected.name && format === "json" && input === JSON.stringify(collected.rows, null, 2);
      setPhase("importing");
      setActivity("Checking and saving your activity…");
      const dataset = useCollected ? { id: collected.dataset_id } : await request<{ id: string }>("/datasets", { method: "POST", body: payload }, signal);
      if (!dataset?.id) throw new Error("Import returned no dataset ID. No analysis was submitted.");
      setPhase("analyzing");
      setActivity("Activity saved. Starting the account comparison…");
      const job = await request<Job>("/swarm/analyze", { method: "POST", body: JSON.stringify({ dataset_id: dataset.id }) }, signal);
      if (!job?.id) throw new Error("The detector returned no job ID. No result has been published.");
      const context: PendingJob = { datasetId: dataset.id, jobId: job.id, name: name.trim(), revision, provenance: useCollected ? "REAL BLUESKY PUBLIC FEEDS" : exampleSource ? `SYNTHETIC INPUT${exampleEdited ? " / EDITED" : ""}` : "USER-PROVIDED INPUT" };
      updatePending(context);
      await track(job, context, operation);
    });
  }

  function cancel() {
    const context = pendingRef.current;
    if (!context) return;
    void operate(async (operation) => {
      setActivity("Requesting server-side cancellation…");
      const job = await request<Job>(`/jobs/${encodeURIComponent(context.jobId)}/cancel`, { method: "POST" }, operation.controller.signal);
      if (job.status === "queued" || job.status === "running") {
        setActivity("Cancellation requested but not confirmed. Resume tracking or request cancellation again.");
      } else await track(job, context, operation);
    });
  }

  function resume() {
    const context = pendingRef.current;
    if (!context) return;
    void operate(async (operation) => {
      setPhase("analyzing");
      setActivity("Checking the server job…");
      const job = await request<Job>(`/jobs/${encodeURIComponent(context.jobId)}`, {}, operation.controller.signal);
      await track(job, context, operation);
    });
  }

  function loadExample(id: string) {
    setCollected(null);
    setExampleId(id);
    const example = examples.find((item) => item.id === id);
    if (!example) return;
    setInput(JSON.stringify(example.rows, null, 2)); setFormat("json"); setName(example.name);
    setEditorOpen(false);
    setExampleSource(example); setExampleEdited(false); setRevision((value) => value + 1); setError("");
  }

  function upload(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_BYTES) { setError("File exceeds 10 MB. The existing editor and graph have not changed."); return; }
    if (!/\.(csv|json)$/i.test(file.name)) { setError("Choose a CSV or JSON file."); return; }
    fileReaderRef.current?.abort();
    const reader = new FileReader(); fileReaderRef.current = reader; setReading(true);
    reader.onload = () => {
      setCollected(null);
      setInput(String(reader.result || "").replace(/^\uFEFF/, ""));
      setEditorOpen(false);
      setFormat(/\.csv$/i.test(file.name) ? "csv" : "json");
      setName(file.name.replace(/\.(csv|json)$/i, "").slice(0, 200) || "Uploaded investigation");
      setExampleId(""); setExampleSource(null); setExampleEdited(false); setRevision((value) => value + 1); setError(""); setReading(false);
    };
    reader.onerror = () => { setError("Could not read the file. The editor and graph have not changed."); setReading(false); };
    reader.readAsText(file);
  }

  function exportResult() {
    if (!snapshot) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot.result, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url;
    anchor.download = `${snapshot.name.replace(/[^a-z0-9_-]+/gi, "-").slice(0, 80) || "swarm"}-result.json`;
    anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  const pairs = useMemo(() => snapshot ? [...snapshot.result.findings].sort((a, b) => Number(b.strong) - Number(a.strong) || b.score - a.score) : [], [snapshot]);
  const disabled = busy || reading || collecting;
  const activeCollection = collected && name === collected.name && format === "json" && input === JSON.stringify(collected.rows, null, 2) ? collected : null;
  return (
    <section className="screen swarm-screen swarm-workbench" id="swarm" aria-labelledby="swarm-title">
      <header className="section-title"><span>03 / FOLLOW THE NETWORK</span><a href="#analysis">↑ CONTENT ANALYSIS</a></header>
      <div className="swarm-intro"><div><p className="swarm-kicker">SPOT THE SWARM / FOLLOW THE EVIDENCE</p><h2 id="swarm-title">Follow the pattern.</h2></div><p>Do the same accounts keep sharing similar posts at nearly the same time? Import public Bluesky profiles, try a demo or add your own activity, then inspect the original posts. A pattern is a reason to investigate—not proof of bots.</p></div>
      <ol className="swarm-steps" aria-label="Investigation steps">
        <li aria-current={!snapshot && !busy ? "step" : undefined}><span>1</span><div><strong>Add activity</strong><small>Fetch Bluesky posts, try a demo or upload</small></div></li>
        <li aria-current={busy ? "step" : undefined}><span>2</span><div><strong>Find repeated patterns</strong><small>Compare wording, links and timing</small></div></li>
        <li aria-current={snapshot && !busy ? "step" : undefined}><span>3</span><div><strong>Read the evidence</strong><small>Compare actual posts, not just scores</small></div></li>
      </ol>
      <ReadingGuide />
      <div className="swarm-layout">
        <div className="swarm-input-column">
          <form className="swarm-panel" onSubmit={(event) => { event.preventDefault(); if (!disabled && !pending) start(); }} aria-label="Swarm investigation input">
            <header className="swarm-panel-heading">1 / ADD ACTIVITY <span>UP TO 5,000 ROWS · 10 MB</span></header>
            <div className="swarm-panel-body">
              <BlueskyImport disabled={busy || reading || !!pending} onBusyChange={setCollecting} onLoad={(value) => {
                setCollected(value); setInput(JSON.stringify(value.rows, null, 2)); setFormat("json"); setName(value.name);
                setExampleId(""); setExampleSource(null); setExampleEdited(false); setEditorOpen(false);
                setRevision((value) => value + 1); setError("");
                setActivity("Real Bluesky posts loaded. Verify the source previews, then click Analyze activity.");
              }} />
              <label className="swarm-field" htmlFor="swarm-example">START WITH A DEMO</label>
              <select id="swarm-example" disabled={disabled || loadingExamples || !examples.length} value={exampleId} onChange={(event) => loadExample(event.target.value)}>
                <option value="">{loadingExamples ? "Loading examples…" : "Choose an example…"}</option>{examples.map((example) => <option key={example.id} value={example.id}>{example.name}</option>)}
              </select>
              {examplesError && <div className="swarm-notice"><p>{examplesError}</p><button type="button" disabled={loadingExamples} onClick={() => setExamplesAttempt((value) => value + 1)}>Retry examples</button></div>}
              {!loadingExamples && !examplesError && !examples.length && <p className="swarm-muted">No examples are available. Upload or paste observations below.</p>}
              {exampleSource && <div className="swarm-example-description"><span className="swarm-evidence-badge">Fictional demo{exampleEdited ? " · edited" : ""}</span><p>{exampleSource.description}</p></div>}
              <p className="swarm-muted">Demo accounts are fictional; the analysis is real. Examples do not measure real-world accuracy.</p>
              <label className="swarm-field" htmlFor="swarm-name">NAME YOUR INVESTIGATION</label>
              <input id="swarm-name" value={name} maxLength={200} disabled={disabled} onChange={(event) => { setName(event.target.value); setRevision((value) => value + 1); }} />
              <label className="swarm-field" htmlFor="swarm-file">OR UPLOAD YOUR OWN CSV / JSON</label>
              <input id="swarm-file" type="file" accept=".json,.csv,application/json,text/csv" disabled={disabled} onChange={(event) => { upload(event.target.files?.[0]); event.target.value = ""; }} />
              <details className="swarm-raw-editor" open={editorOpen} onToggle={(event) => setEditorOpen(event.currentTarget.open)}>
              <summary>{input ? "View or edit the raw data" : "Or paste JSON / CSV"}</summary>
              <div className="swarm-editor-heading"><label htmlFor="swarm-input">ACTIVITY DATA</label><select aria-label="Input format" value={format} disabled={disabled} onChange={(event) => { setFormat(event.target.value as InputFormat); if (exampleSource) setExampleEdited(true); setRevision((value) => value + 1); }}><option value="json">JSON array</option><option value="csv">CSV</option></select></div>
              <textarea id="swarm-input" value={input} disabled={disabled} spellCheck={false} aria-describedby="swarm-fields" placeholder={format === "json" ? "Paste a JSON array of event objects, or load an example above." : "account_id,content_id,action,timestamp,text,url,platform"} onChange={(event) => { setInput(event.target.value); if (exampleSource) setExampleEdited(true); setRevision((value) => value + 1); }} />
              <div className="swarm-editor-meta"><span>{number(new Blob([input]).size)} bytes</span><button type="button" disabled={disabled || !input} onClick={() => { setInput(""); setExampleSource(null); setExampleId(""); setExampleEdited(false); setRevision((value) => value + 1); }}>Clear input</button></div>
              <details id="swarm-fields" className="swarm-field-guide"><summary>Input fields &amp; timestamp requirements</summary><p>Fields: account_id, content_id, action, timestamp, text, url, platform. JSON must be an array of objects; CSV needs a header row. Quote CSV fields containing commas or newlines.</p><p>Actions: created, reposted, replied_to, liked. Each interaction must reference content with a created observation; each content_id must have a consistent author and content.</p><p>Use ISO 8601 timestamps with Z or a UTC offset, e.g. 2026-11-14T09:00:00Z. Missing timestamps and likes are excluded by the detector and may lead to insufficient data.</p><p>Created content needs text or a URL. Source validation on the server is authoritative.</p></details>
              </details>
              <p className="swarm-muted swarm-privacy-note">Stored on this server · no LLM calls. Only upload data you have permission to use.</p>
              <button type="submit" className="swarm-run" disabled={disabled || !!pending || !input.trim()}>{reading ? "Reading file…" : busy ? "Analyzing…" : "Analyze activity →"}</button>
              {!input.trim() && <p className="swarm-run-hint">Choose a demo or add a file to get started.</p>}
              {collected && !activeCollection && <p className="swarm-notice">The name or raw data was edited. This will be saved as user-provided input, without claiming server-verified Bluesky provenance.</p>}
              <InputPreview input={input} format={format} collected={activeCollection} />
              {activeCollection && <CollectionCoverage collection={activeCollection.collection} datasetId={activeCollection.dataset_id} />}
            </div>
          </form>
          <div className="swarm-panel swarm-job-panel" aria-busy={busy}>
            <header className="swarm-panel-heading">ANALYSIS PROGRESS / {busy ? "WORKING" : pending ? "CHECK STATUS" : "READY"}</header>
            <div className="swarm-panel-body">
              {busy && <ol className="swarm-run-progress" aria-label="Analysis progress">{(["importing", "analyzing", "loading"] as const).map((step, index) => <li key={step} aria-current={phase === step ? "step" : undefined}><span>{index + 1}</span>{step === "importing" ? "Check & save activity" : step === "analyzing" ? "Compare repeated patterns" : "Prepare evidence & map"}</li>)}</ol>}
              <p role="status" aria-live="polite">{activity}</p>
              {pending && <><div className="swarm-actions"><button type="button" onClick={cancel}>Cancel server job</button>{!busy && <button type="button" onClick={resume}>Resume tracking</button>}</div><details><summary>Analysis reference</summary><p className="swarm-muted">Job: {pending.jobId}</p></details></>}
              {busy && !pending && <p className="swarm-muted">Cancellation is available once the server returns a job ID.</p>}
              <details><summary>Connection &amp; timeout details</summary><p className="swarm-muted">30 s per request · 11 min tracking limit · no automatic retries.</p></details>
              {error && <div className="swarm-error" role="alert"><strong>Unable to publish a new result</strong><p>{error}</p></div>}
              {snapshot && <p className="swarm-notice">{busy || error || snapshot.revision !== revision ? "Previous completed result remains visible: " : "Showing completed result: "}{snapshot.name}. {snapshot.revision !== revision && "The editor differs from this result; import and run to update it."}</p>}
            </div>
          </div>
        </div>
        <div className="swarm-results-column">
          {!snapshot ? <div className="swarm-panel swarm-welcome"><span className="swarm-crosshair">↗</span><p className="swarm-kicker">YOUR FIRST INVESTIGATION</p><h3>Start with a story, not a spreadsheet.</h3><p>Load a demo to see what repeated coordination looks like, then click <strong>Analyze activity</strong>. You’ll get an explanation, account groups, and the actual posts behind each match.</p>
            <div className="swarm-demo-cards">{examples.map((example, index) => <button type="button" key={example.id} disabled={disabled} aria-pressed={exampleId === example.id} onClick={() => loadExample(example.id)}><span className="swarm-demo-number">0{index + 1}</span><strong>{example.name.replace(/^Synthetic /, "")}</strong><span>{example.id === "coordinated-network" ? "Repeated matching posts · learn to read the evidence" : example.id === "benign-announcement" ? "A one-off shared announcement · compare the contrast" : "Missing timing evidence · see when we cannot conclude"}</span><span className="swarm-demo-cta">{exampleId === example.id ? "Loaded · analyze when ready" : "Load this demo →"}</span></button>)}</div>
            {exampleId && <button type="button" className="swarm-quick-run" disabled={disabled || !!pending || !input.trim()} onClick={start}>Analyze loaded demo →</button>}
            {!examples.length && <p className="swarm-muted">{loadingExamples ? "Loading demos…" : "Demos aren’t available right now. You can still upload a file or paste activity."}</p>}
            <p className="swarm-muted">All demos are fictional inputs run through the real detector. No precomputed verdicts.</p></div> : <>
            <ResultSummary snapshot={snapshot} exportResult={exportResult} />
            <div className="swarm-evidence-grid" id="swarm-evidence">
              <section className="swarm-panel swarm-selection" aria-label="Select investigation evidence">
                <header className="swarm-panel-heading">3 / FOLLOW THE EVIDENCE</header>
                <div className="swarm-panel-body">
                  <h4>Account groups <span className="swarm-count-pill">{snapshot.result.clusters.length}</span></h4>
                  <p className="swarm-muted">A group has at least three accounts, with a flagged connection between every pair. “Cluster” means the same thing.</p>
                  <div className="swarm-groups">{snapshot.result.clusters.map((cluster) => <button type="button" key={cluster.id} aria-pressed={selection?.kind === "cluster" && selection.id === cluster.id} onClick={() => setSelection({ kind: "cluster", id: cluster.id })}><span>{groupLabel(cluster.id, snapshot)} <span className="swarm-group-arrow">↗</span></span><span>{cluster.account_ids.length} accounts · {cluster.account_ids.length * (cluster.account_ids.length - 1) / 2} mutual pair connections</span><span>{cluster.account_ids.map((id) => entityLabel(id, snapshot)).join(", ")}</span></button>)}</div>
                  {!snapshot.result.clusters.length && <p className="swarm-muted">No strong groups returned. A flagged pair can still appear below; no groups is not a safety verdict.</p>}
                  <label className="swarm-field" htmlFor="swarm-pair">OR CHOOSE AN ACCOUNT PAIR / {pairs.length}</label>
                  <select id="swarm-pair" disabled={!pairs.length} value={selection?.kind === "pair" ? selection.id : ""} onChange={(event) => { if (event.target.value) setSelection({ kind: "pair", id: event.target.value }); }}><option value="">{pairs.length ? "Select pair evidence…" : "No pair findings returned"}</option>{pairs.map((pair) => <option key={pair.id} value={pair.id}>{entityLabel(pair.source_id, snapshot)} ↔ {entityLabel(pair.target_id, snapshot)} · {pair.strong ? "strong" : "candidate"}</option>)}</select>
                  <div className="swarm-pair-list">{pairs.slice(0, 6).map((pair) => <button type="button" key={pair.id} aria-pressed={selection?.kind === "pair" && selection.id === pair.id} onClick={() => setSelection({ kind: "pair", id: pair.id })}><span>{entityLabel(pair.source_id, snapshot)} <b>↔</b> {entityLabel(pair.target_id, snapshot)}</span><small>{pair.episode_count} matching occasions · {pair.strong ? "flagged pair" : "candidate only"}</small></button>)}</div>
                  {pairs.length > 6 && <p className="swarm-muted">Showing the first 6 pairs. Use the selector for all {pairs.length}.</p>}
                  <details><summary>Browse individual agents &amp; posts</summary><label className="swarm-field" htmlFor="swarm-entity">ITEMS IN THE MAP / {snapshot.graph.nodes.length}</label>
                  <select id="swarm-entity" value={selection?.kind === "entity" && snapshot.graph.nodes.some((node) => node.id === selection.id) ? selection.id : ""} onChange={(event) => { if (event.target.value) setSelection({ kind: "entity", id: event.target.value }); }}><option value="">Select an item…</option>{snapshot.graph.nodes.map((node) => <option key={node.id} value={node.id}>{node.kind === "content" ? "post" : node.kind} / {entityLabel(node.id, snapshot)}</option>)}</select></details>
                  <details><summary>Dataset &amp; job identifiers</summary><p>Dataset: {snapshot.datasetId}</p><p>Job: {snapshot.jobId}</p></details>
                </div>
              </section>
              <EvidenceInspector key={`${snapshot.jobId}:${selection?.kind}:${selection?.id}`} snapshot={snapshot} selection={selection} select={setSelection} />
            </div>
            <ObservationGraph key={`${snapshot.datasetId}:${snapshot.jobId}`} snapshot={snapshot} selection={selection} select={setSelection} />
          </>}
        </div>
      </div>
      <footer className="swarm-disclaimer">Coordination ≠ bots or malice. Investigate context, provenance, and alternative explanations. Synthetic examples ≠ benchmark.</footer>
    </section>
  );
}