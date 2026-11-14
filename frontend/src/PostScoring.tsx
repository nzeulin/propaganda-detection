import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, features, labels, type Feature } from "./types";

type Screening = {
  label: "not_propaganda" | "requires_further_analysis" | "propaganda";
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
};
type ScoringJob = {
  id: string;
  status: string;
  error?: { message?: string } | null;
  result?: { features: Record<Feature, number | null>; propaganda_screening: Screening; analysis_id: string } | null;
};
const ScoringContext = createContext<{
  scores: Record<string, ContentScore>;
  score: (contentId: string) => void;
} | null>(null);

export function PostScoringProvider({ initial, children }: { initial?: Record<string, ContentScore>; children: ReactNode }) {
  const [scores, setScores] = useState<Record<string, ContentScore>>(initial || {});
  const requests = useRef(new Map<string, AbortController>());

  useEffect(() => () => {
    for (const controller of requests.current.values()) controller.abort();
    requests.current.clear();
  }, []);

  async function score(contentId: string) {
    if (requests.current.has(contentId) || scores[contentId]?.screening?.complete) return;
    const controller = new AbortController();
    requests.current.set(contentId, controller);
    const signal = controller.signal;
    let timedOut = false;
    const deadline = window.setTimeout(() => { timedOut = true; controller.abort(); }, 11 * 60 * 1000);
    setScores(current => ({ ...current, [contentId]: { ...current[contentId], pending: true, error: undefined } }));
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
      } }));
    } catch (error) {
      if (signal.aborted && !timedOut) return;
      const message = timedOut ? "Tracking timed out. Click Retry scoring to check or restart the saved job."
        : error instanceof Error ? error.message : "Scoring unavailable. Retry explicitly.";
      setScores(current => ({ ...current, [contentId]: { ...current[contentId], pending: false, error: message } }));
    } finally {
      window.clearTimeout(deadline);
      requests.current.delete(contentId);
    }
  }

  return <ScoringContext.Provider value={{ scores, score }}>{children}</ScoringContext.Provider>;
}

export function usePostScoring() {
  const context = useContext(ScoringContext);
  if (!context) throw new Error("Post scoring requires its dataset provider.");
  return context;
}

export function PostScoring({ contentId }: { contentId: string }) {
  const { scores, score } = usePostScoring();
  const result = scores[contentId];
  const screening = result?.screening;
  const label = screening?.label === "propaganda" ? "Propaganda"
    : screening?.label === "not_propaganda" ? "Not propaganda" : "Requires further analysis";
  return <div className="swarm-content-scoring">
    <p role="status" title={screening ? `${screening.reason} Heuristic thresholds: ${screening.thresholds.review} / ${screening.thresholds.propaganda}.` : undefined}>
      {result?.pending ? "Scoring post…" : screening ? label : result?.error ? "Scoring unavailable" : "Not scored"}
    </p>
    {(!screening?.complete || result?.error) && <button type="button" disabled={result?.pending}
      title="Uses configured AI models to score this post. External validation is not run."
      onClick={() => void score(contentId)}>{result?.pending ? "Scoring…" : result?.error || screening ? "Retry scoring" : "Score post"}</button>}
    {result?.error && <p className="swarm-error" role="alert">{result.error}</p>}
    {result?.features && <details><summary>Propaganda features</summary><dl>
      {features.map(feature => <div key={feature}><dt>{labels[feature]}</dt><dd>{result.features?.[feature]?.toFixed(2) ?? "Not assessed"}</dd></div>)}
    </dl></details>}
  </div>;
}
