import React, { useState } from "react";
import { features, labels, type Analysis, type Annotation } from "./types";
import { segmentText } from "./highlights";
const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const scoreLabel = (value: number | null) =>
  value === null ? "—" : value.toFixed(3);
function Article({ result }: { result: Analysis }) {
  const [selected, setSelected] = useState<Annotation[]>([]);
  const segments = segmentText(
    result.normalized_text,
    result.annotations,
    result.highlight_thresholds,
  );
  return (
    <div className="article-layout">
      <section className="panel article-panel" aria-labelledby="article-title">
        <div className="panel-heading">
          <h2 id="article-title">Annotated article</h2>
          <span className="mono">UNICODE SOURCE SPANS</span>
        </div>
        <div className="legend">
          <span>
            <i className="yellow-dot" />
            Clear local indicator ≥{" "}
            {result.highlight_thresholds.yellow.toFixed(2)}
          </span>
          <span>
            <i className="red-dot" />
            Strong ≥ {result.highlight_thresholds.red.toFixed(2)}
          </span>
        </div>
        <p className="small muted">
          Select or keyboard-focus a passage to inspect all associated findings.
          Color describes local severity; article contribution depends on weight
          and coverage.
        </p>
        <div className="article-text">
          {segments.map((segment) =>
            segment.severity ? (
              <mark
                key={segment.start}
                className={`highlight ${segment.severity}`}
                tabIndex={0}
                role="button"
                aria-label={`${segment.severity === "red" ? "Strong" : "Clear"} local indicator: ${segment.findings.map((a) => labels[a.feature]).join(", ")}. ${segment.text}`}
                onFocus={() => setSelected(segment.findings)}
                onClick={() => setSelected(segment.findings)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelected(segment.findings);
                  }
                }}
              >
                {segment.text}
              </mark>
            ) : (
              <React.Fragment key={segment.start}>
                {segment.text}
              </React.Fragment>
            ),
          )}
        </div>
      </section>
      <aside
        className="panel evidence-panel"
        aria-label="Passage evidence"
        aria-live="polite"
      >
        <div className="panel-heading">
          <h2>Evidence inspector</h2>
          <span className="cyan">↗</span>
        </div>
        {selected.length === 0 ? (
          <div className="empty-evidence">
            <span className="inspect-symbol">⌖</span>
            <h3>Follow the evidence</h3>
            <p>
              Select a highlighted passage to see the technique, attribution,
              rubric and exact contribution.
            </p>
            {!result.annotations.length && (
              <p>No passages met the local highlight thresholds.</p>
            )}
          </div>
        ) : (
          selected.map((finding) => (
            <div className="finding" key={finding.id}>
              <div className="eyebrow">{labels[finding.feature]}</div>
              <blockquote>{finding.excerpt}</blockquote>
              <div className="finding-numbers">
                <div>
                  <small>LOCAL SCORE</small>
                  <strong>{scoreLabel(finding.score)}</strong>
                </div>
                <div>
                  <small>ARTICLE CONTRIBUTION</small>
                  <strong>{scoreLabel(finding.contribution)}</strong>
                </div>
              </div>
              <p className="small">
                {finding.speaker_name || finding.speaker.replaceAll("_", " ")} ·{" "}
                {finding.attribution}
              </p>
              <p className="small muted">
                {finding.contribution_scope === "material_level"
                  ? "Contextual finding: score belongs to the full material and is not allocated to this passage."
                  : "Contribution belongs to the canonical claim, counted once across all repeated occurrences. It may be diagnostic when material coverage is insufficient."}
              </p>
              <details>
                <summary>Five-level rubric & provider record</summary>
                <ol start={0}>
                  {finding.rubric.map((level) => (
                    <li key={level}>{level}</li>
                  ))}
                </ol>
                <p className="mono small">
                  Raw: {finding.assessment.raw_score.toFixed(3)} / 4<br />
                  Confidence: {scoreLabel(finding.assessment.confidence)}
                  <br />
                  Model: {finding.assessment.model}
                </p>
                <p className="small muted">
                  Level distribution:{" "}
                  {finding.assessment.probabilities
                    .map((p) => p.toFixed(3))
                    .join(" · ")}
                  . Confidence is concentration, not validated accuracy.
                </p>
              </details>
            </div>
          ))
        )}
      </aside>
    </div>
  );
}

export function Results({ result }: { result: Analysis }) {
  const label = result.classification.label;
  const failure = result.warnings.find(
    (warning) =>
      warning.startsWith("Scoring unavailable") ||
      warning.startsWith("extraction_failed:"),
  );
  return (
    <div className="results" key={result.material_id}>
      <section className="result-banner panel" aria-live="polite">
        <div>
          <div className="eyebrow">
            {result.demo ? "OFFLINE SYNTHETIC DEMO" : "LIVE CONTENT ANALYSIS"}
          </div>
          <h2>
            {label === "indicators_detected"
              ? "Manipulation indicators detected"
              : label === "inconclusive"
                ? "Assessment inconclusive"
                : "No strong text indicators"}
          </h2>
          <p className="muted">
            Experimental screening · {result.classification.policy_version} ·
            Overall risk score: not assessed
          </p>
        </div>
        <span
          className={`status-orb ${label === "indicators_detected" ? "caution" : ""}`}
        >
          {label === "inconclusive" ? "?" : "◎"}
        </span>
      </section>
      {failure && (
        <p className="error" role="alert">
          Some assessments could not be completed. {failure}
        </p>
      )}
      <section className="narrative">
        <div className="eyebrow">
          {result.narratives.length > 1
            ? "CENTRAL NARRATIVES"
            : "CENTRAL NARRATIVE"}
        </div>
        {result.narratives.length > 1 ? (
          <ul>
            {result.narratives.map((narrative) => (
              <li key={narrative.id}>{narrative.summary}</li>
            ))}
          </ul>
        ) : (
          <p>{result.primary_narrative || "No valid narrative extracted."}</p>
        )}
        {result.review_required && (
          <p className="notice">
            Narrative review is required. The combined profile is withheld;
            available scores below are diagnostic, not a final assessment.
          </p>
        )}
      </section>
      <section className="panel profile">
        <div className="panel-heading">
          <h2>Seven-feature profile</h2>
          <span className="mono">OBSERVED STRENGTH · 0–1</span>
        </div>
        <div className="meters">
          {features.map((feature, index) => {
            const published = result.features[feature];
            const detail = result.feature_details[feature];
            const diagnostic = result.diagnostics?.[feature];
            // Diagnostic estimates remain separate from the published classification.
            const value = published ?? diagnostic?.partial_estimate ?? null;
            const isDiagnostic = published === null && value !== null;
            const coverage = isDiagnostic
              ? diagnostic!.coverage
              : detail.coverage;
            return (
              <div className="meter" key={feature}>
                <div className="meter-title">
                  <span className="mono muted">0{index + 1}</span>
                  <h3>{labels[feature]}</h3>
                  <strong>
                    {isDiagnostic && (
                      <span className="diagnostic-label">Diagnostic</span>
                    )}
                    {value === null ? "Not assessed" : value.toFixed(3)}
                  </strong>
                </div>
                <div
                  className="meter-track"
                  role={value === null ? "img" : "meter"}
                  aria-label={`${labels[feature]}${isDiagnostic ? ": Diagnostic" : value === null ? ": Not assessed" : ""}`}
                  {...(value === null
                    ? {}
                    : {
                        "aria-valuenow": value,
                        "aria-valuemin": 0,
                        "aria-valuemax": 1,
                      })}
                >
                  <div
                    style={{ width: value === null ? "0%" : percent(value) }}
                  />
                </div>
                <p>
                  {value === null
                    ? detail.reason
                    : `${percent(coverage)} coverage · ${detail.scope.replaceAll("_", " ")}${isDiagnostic ? ` · ${detail.reason}` : ""}`}
                </p>
              </div>
            );
          })}
        </div>
      </section>
      <Article result={result} />
      <details className="panel provenance">
        <summary>Assessment limits & provenance</summary>
        <ul>
          {result.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
        <p className="mono small">
          Extractor: {result.model_versions.extractor}
          <br />
          Scorer: {result.model_versions.scorer}
          <br />
          Rubrics: {result.versions.rubrics}
          <br />
          Aggregation: {result.provenance.aggregation}
          <br />
          SHA-256: {result.provenance.content_sha256}
        </p>
      </details>
    </div>
  );
}
