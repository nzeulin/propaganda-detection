import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, features, formatFeatureScore, labels, type Analysis, type Feature } from "./types";

type Screening = {
  label: "not_propaganda" | "requires_further_analysis" | "propaganda";
  weighted_score: number | null;
  complete: boolean;
  reason: string;
  thresholds: { review: number; propaganda: number };
};
export type ContentScore = {
  features?: Record<Feature, number | null>;
  screening?: Screening;
  job_id?: string;
  analysis_id?: string;
  pending?: boolean;
  error?: string;
  feature_details?: Analysis["feature_details"];
  attribution_note?: string;
  details_loading?: boolean;
  details_error?: string;
};
type ScoringResult = {
  features: Record<Feature, number | null>;
  propaganda_screening: Screening;
  feature_details?: Analysis["feature_details"];
  statements?: { author_attributable: boolean; stance: string }[];
};
type ScoringJob = {
  id: string;
  status: string;
  error?: { message?: string } | null;
  result?: (ScoringResult & { analysis_id: string }) | null;
};

function scoreDetails(result: ScoringResult) {
  const claims = result.statements;
  const noEndorsedClaims = claims?.length && !claims.some(claim => claim.author_attributable && claim.stance === "endorsed");
  return {
    feature_details: result.feature_details,
    attribution_note: noEndorsedClaims
      ? "No author-endorsed statements were available for emotional, logical or authority scoring."
        + (claims.every(claim => claim.stance === "neutrally_reported" || claim.stance === "rejected")
          ? " Neutral or rejected source claims are excluded from these features." : "")
      : undefined,
  };
}

const ScoringContext = createContext<{
  scores: Record<string, ContentScore>;
  queue: string[];
  score: (contentId: string) => void;
  loadDetails: (contentId: string) => void;
} | null>(null);

export function PostScoringProvider({ initial, autoScoreIds = [], children }: {
  initial?: Record<string, ContentScore>; autoScoreIds?: string[]; children: ReactNode;
}) {
  const [scores, setScores] = useState<Record<string, ContentScore>>(initial || {});
  // Each provider belongs to one graph run; reuse complete cached screenings.
  const [queue, setQueue] = useState(() => [...new Set(autoScoreIds)].filter(id => !initial?.[id]?.screening?.complete));
  const requests = useRef(new Map<string, AbortController>());

  useEffect(() => () => {
    for (const controller of requests.current.values()) controller.abort();
    requests.current.clear();
  }, []);

  function score(contentId: string) {
    if (scores[contentId]?.screening?.complete) return;
    setQueue(current => current.includes(contentId) ? current : [...current, contentId]);
  }

  useEffect(() => {
    // Keep active IDs in the queue until settled, so either slot can finish first.
    for (const contentId of queue.slice(0, 2)) {
      if (!requests.current.has(contentId)) void run(contentId);
    }
  }, [queue]);

  async function run(contentId: string) {
    requests.current.get(`details:${contentId}`)?.abort();
    const controller = new AbortController();
    requests.current.set(contentId, controller);
    const signal = controller.signal;
    let timedOut = false;
    const deadline = window.setTimeout(() => { timedOut = true; controller.abort(); }, 11 * 60 * 1000);
    setScores(current => ({ ...current, [contentId]: {
      ...current[contentId], pending: true, error: undefined, details_loading: false, details_error: undefined,
    } }));
    try {
      let job = await api<ScoringJob>("/api/v1/content/analyze", { content_id: contentId, verification: "none" }, signal);
      while (job.status === "queued" || job.status === "running") {
        await new Promise<void>((resolve, reject) => {
          const stop = () => { window.clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); };
          const timer = window.setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, 1500);
          if (signal.aborted) stop();
          else signal.addEventListener("abort", stop, { once: true });
        });
        job = await api<ScoringJob>(`/api/v1/jobs/${encodeURIComponent(job.id)}`, undefined, signal);
      }
      if (signal.aborted) return;
      if (job.status !== "completed") throw new Error(job.error?.message || `Scoring ${job.status}. Retry explicitly.`);
      if (!job.result?.propaganda_screening || !job.result.features) throw new Error("Scoring returned no usable decision.");
      const result = job.result;
      setScores(current => ({ ...current, [contentId]: {
        features: result.features, screening: result.propaganda_screening, job_id: job.id, analysis_id: result.analysis_id,
        ...scoreDetails(result),
      } }));
    } catch (error) {
      if (signal.aborted && !timedOut) return;
      const message = timedOut ? "Tracking timed out. Click Retry scoring to check or restart the saved job."
        : error instanceof Error ? error.message : "Scoring unavailable. Retry explicitly.";
      setScores(current => ({ ...current, [contentId]: { ...current[contentId], pending: false, error: message } }));
    } finally {
      window.clearTimeout(deadline);
      // An aborted instance must not remove a replacement request or its queue entry.
      if (requests.current.get(contentId) === controller) {
        requests.current.delete(contentId);
        setQueue(current => current.filter(id => id !== contentId));
      }
    }
  }

  async function loadDetails(contentId: string) {
    const entry = scores[contentId];
    const key = `details:${contentId}`;
    if (!entry?.analysis_id || entry.feature_details || entry.pending || requests.current.has(key)) return;
    const revision = entry.analysis_id;
    const controller = new AbortController();
    requests.current.set(key, controller);
    let timedOut = false;
    const deadline = window.setTimeout(() => { timedOut = true; controller.abort(); }, 30_000);
    setScores(current => ({ ...current, [contentId]: { ...current[contentId], details_loading: true, details_error: undefined } }));
    try {
      const saved = await api<{ id: string; result: ScoringResult }>(
        `/api/v1/content/${encodeURIComponent(contentId)}/analysis?revision=${encodeURIComponent(revision)}`,
        undefined, controller.signal,
      );
      if (controller.signal.aborted) return;
      if (saved.id !== revision || !saved.result?.feature_details) throw new Error("Saved feature explanations are unavailable.");
      setScores(current => current[contentId]?.analysis_id === revision && !current[contentId]?.pending
        ? { ...current, [contentId]: { ...current[contentId], ...scoreDetails(saved.result), details_loading: false } }
        : current);
    } catch (error) {
      if (controller.signal.aborted && !timedOut) return;
      const message = timedOut ? "Loading score explanations timed out. Try again."
        : error instanceof Error ? error.message : "Could not load saved feature explanations.";
      setScores(current => current[contentId]?.analysis_id === revision && !current[contentId]?.pending
        ? { ...current, [contentId]: { ...current[contentId], details_loading: false, details_error: message } }
        : current);
    } finally {
      window.clearTimeout(deadline);
      if (requests.current.get(key) === controller) requests.current.delete(key);
    }
  }

  return <ScoringContext.Provider value={{ scores, queue, score, loadDetails }}>{children}</ScoringContext.Provider>;
}

export function usePostScoring() {
  const context = useContext(ScoringContext);
  if (!context) throw new Error("Post scoring requires its dataset provider.");
  return context;
}

export function PostScoring({ contentId }: { contentId: string }) {
  const { scores, queue, score, loadDetails } = usePostScoring();
  const result = scores[contentId];
  const queued = queue.includes(contentId) && !result?.pending;
  const screening = result?.screening;
  const label = screening?.label === "propaganda" ? "Propaganda"
    : screening?.label === "not_propaganda" ? "Not propaganda" : "Requires further analysis";
  return <div className="swarm-content-scoring">
    <p role="status" title={screening ? `${screening.reason} Review at ${screening.thresholds.review * 100}/100; propaganda at ${screening.thresholds.propaganda * 100}/100.` : undefined}>
      {result?.pending ? "Scoring post…" : queued ? "Queued for scoring" : result?.error ? "Scoring unavailable" : screening
        ? `${label}${screening.weighted_score == null ? "" : ` · ${Math.round(screening.weighted_score * 100)}/100`}` : "Not scored"}
    </p>
    {(!screening?.complete || result?.error) && <button type="button" disabled={result?.pending || queued}
      title="Uses configured AI models to score this post. External validation is not run."
      onClick={() => score(contentId)}>{result?.pending ? "Scoring…" : queued ? "Queued" : result?.error || screening ? "Retry scoring" : "Score post"}</button>}
    {result?.error && <p className="swarm-error" role="alert">{result.error}</p>}
    {result?.features && <details onToggle={event => { if (event.currentTarget.open) void loadDetails(contentId); }}>
      <summary>Propaganda features</summary>
      {result.details_loading && <p role="status">Loading score explanations…</p>}
      {result.details_error && <div role="alert"><p>{result.details_error}</p>
        <button type="button" onClick={() => void loadDetails(contentId)}>Retry explanations</button></div>}
      {result.attribution_note && <p>{result.attribution_note}</p>}
      <dl>{features.map(feature => {
        const value = result.features?.[feature];
        const detail = result.feature_details?.[feature];
        return <div key={feature}><dt>{labels[feature]}</dt><dd>{formatFeatureScore(feature, value, "Not assessed")}</dd>
          {value == null && detail && <dd className="swarm-feature-reason">
            {detail.reason} Coverage: {(detail.coverage * 100).toFixed(0)}%.
          </dd>}
        </div>;
      })}</dl>
    </details>}
  </div>;
}
