import { Fragment, useEffect, useState } from "react";
import type { components } from "./contracts";
import { segmentText } from "./highlights";
import { api, type Analysis } from "./types";

type Report = components["schemas"]["AttributionReviewReport"];
const decisionLabels = {
  keep: "Keep highlight",
  exclude: "Exclude from reviewed highlights",
  needs_review: "Needs review",
};

export function AttributionReview({ result }: { result: Analysis }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const annotations = result.annotations.map(
      ({ id, start, end, excerpt }) => ({
        id,
        start,
        end,
        excerpt,
      }),
    );
    api<Report>(
      "/api/v1/attribution-review",
      { normalized_text: result.normalized_text, annotations },
      controller.signal,
    )
      .then(setReport)
      .catch((cause) => {
        if (!controller.signal.aborted) setError(cause.message);
      });
    return () => controller.abort();
  }, [result]);

  if (error) return <p role="alert">Context check unavailable. {error}</p>;
  if (!report) return <p role="status">Checking quote context…</p>;

  const changed = report.passages.some(({ decision }) => decision !== "keep");
  const kept = new Set(report.kept_annotation_ids);
  const reviewedText = changed
    ? segmentText(
        result.normalized_text,
        result.annotations.filter(({ id }) => kept.has(id)),
        result.highlight_thresholds,
      )
    : [];

  return (
    <>
      <p className="small muted">
        Checks explicit English quote and reporting context. Decisions apply to
        the reviewed highlights. The article scores still show the first pass.
      </p>
      {!report.passages.length && <p>No highlights to check.</p>}
      {report.passages.map(({ passage, decision, reason, evidence = [] }) => (
        <div className="finding" key={`${passage.start}:${passage.end}`}>
          <h3>{decisionLabels[decision]}</h3>
          <blockquote>{passage.excerpt}</blockquote>
          <p>{reason}</p>
          {evidence.length > 0 && (
            <ul aria-label="Context evidence">
              {evidence.map((cue) => (
                <li key={`${cue.start}:${cue.end}`}>“{cue.excerpt}”</li>
              ))}
            </ul>
          )}
        </div>
      ))}
      {changed ? (
        <section aria-label="Reviewed highlights">
          <h3>Reviewed highlights</h3>
          <div className="article-text">
            {reviewedText.map((segment) =>
              segment.severity ? (
                <mark
                  key={segment.start}
                  className={`highlight ${segment.severity}`}
                >
                  {segment.text}
                </mark>
              ) : (
                <Fragment key={segment.start}>{segment.text}</Fragment>
              ),
            )}
          </div>
        </section>
      ) : (
        report.passages.length > 0 && <p>All original highlights are kept.</p>
      )}
    </>
  );
}
