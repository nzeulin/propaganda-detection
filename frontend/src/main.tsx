/// <reference types="vite/client" />
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import SwarmNetwork from "./SwarmNetwork";
import {
  api,
  features,
  labels,
  type Analysis as AnalysisResult,
  type Claim,
  type Feature,
} from "./types";
import { segmentText } from "./highlights";

const article =
  "Officials insist the proposal is the only responsible path, despite independent reporting that documents unresolved costs. Anyone questioning the plan is accused of putting public safety at risk. The same warning appeared repeatedly across coordinated accounts before the committee vote.";

function Meter({
  name,
  score,
  reason,
}: {
  name: Feature;
  score: number | null | undefined;
  reason?: string;
}) {
  return (
    <div className="meter">
      <div>
        <span>{labels[name]}</span>
        <button
          className="info"
          title={reason || "Observed strength from 0.00 to 1.00."}
          aria-label={`About ${labels[name]}`}
        >
          [i]
        </button>
        <b>{score == null ? "Unavailable" : score.toFixed(2)}</b>
      </div>
      <div className="track">
        <i style={{ width: `${(score ?? 0) * 100}%` }} />
      </div>
    </div>
  );
}

type StatementViewProps = {
  statement: Claim;
  selected: boolean;
  registerElement: (element: HTMLElement | null) => void;
};

function StatementView({
  statement,
  selected,
  registerElement,
}: StatementViewProps) {
  const [review, setReview] = useState("UNREVIEWED");

  return (
    <article
      className={`statement ${selected ? "selected-statement" : ""}`}
      ref={registerElement}
    >
      <header>
        <span>
          {(statement.speaker_name || statement.speaker).replaceAll("_", " ")} ·{" "}
          {statement.stance.replaceAll("_", " ")}
        </span>
      </header>

      <p className="statement-text">{statement.text}</p>

      <div className="tags">
        {statement.techniques.map((technique, index) => (
          <span key={index} title={technique.explanation}>
            {technique.technique.replaceAll("_", " ")}
            <em title={technique.explanation}>[i]</em>
          </span>
        ))}
      </div>

      <div className="feature-grid">
        {features.map((name) => (
          <Meter key={name} name={name} score={statement.features[name]} />
        ))}
      </div>

      <footer className="review">
        <span>Review status: {review.toLowerCase()}</span>
        <div>
          <button onClick={() => setReview("CONFIRMED")}>Confirm</button>
          <button onClick={() => setReview("FALSE POSITIVE")}>
            Dismiss / false positive
          </button>
          <button onClick={() => setReview("NEEDS REVIEW")}>
            Needs review
          </button>
        </div>
      </footer>
    </article>
  );
}

function Analysis() {
  const [input, setInput] = useState(article);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedStatementId, setSelectedStatementId] = useState<string | null>(
    null,
  );
  const controller = useRef<AbortController | null>(null);
  const resultElements = useRef<Record<string, HTMLElement | null>>({});
  const resultsColumn = useRef<HTMLDivElement | null>(null);
  const characterCount = Array.from(input).length;

  useEffect(() => () => controller.current?.abort(), []);

  function updateInput(value: string) {
    setInput(value);
    setResult(null);
    setError("");
    setSelectedStatementId(null);
  }

  async function analyze() {
    if (controller.current || !input.trim() || characterCount > 40000) return;
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    setResult(null);
    setError("");
    setSelectedStatementId(null);
    try {
      const response = await api<AnalysisResult>(
        "/analyze",
        { text: input, include_details: true },
        request.signal,
      );
      if (!request.signal.aborted) {
        setResult(response);
        setSelectedStatementId(response.statements[0]?.id ?? null);
      }
    } catch (err) {
      if (!request.signal.aborted) {
        setError(
          err instanceof Error ? err.message : "Analysis failed. Try again.",
        );
      }
    } finally {
      controller.current = null;
      if (!request.signal.aborted) setLoading(false);
    }
  }

  function selectStatement(statementId: string) {
    setSelectedStatementId(statementId);
    requestAnimationFrame(() => {
      const panel = resultsColumn.current;
      const statement = resultElements.current[statementId];
      if (!panel || !statement) return;
      const panelBounds = panel.getBoundingClientRect();
      const statementBounds = statement.getBoundingClientRect();
      panel.scrollTo({
        top: panel.scrollTop + statementBounds.top - panelBounds.top - 12,
        behavior: "smooth",
      });
    });
  }

  const segments = result
    ? segmentText(
      result.normalized_text,
      result.annotations,
      result.highlight_thresholds,
    )
    : [];

  return (
    <section
      className="screen analysis-screen"
      id="analysis"
      aria-busy={loading}
    >
      <div className="input-column">
        <header className="section-title">
          <span>Text analysis</span>
        </header>

        <div className="input-meta">
          <span>{characterCount.toLocaleString()} / 40,000 characters</span>
          {result && (
            <button className="edit-input" onClick={() => updateInput(input)}>
              Edit text
            </button>
          )}
        </div>

        {result ? (
          <div className="input-highlighter" aria-label="Analyzed article text">
            {segments.map((segment) => {
              const statementId = segment.findings.find((finding) =>
                result.statements.some(
                  (statement) => statement.id === finding.claim_id,
                ),
              )?.claim_id;
              const title = segment.findings
                .map((finding) => labels[finding.feature])
                .join(", ");
              const className = `sentence-highlight highlight-${segment.severity} ${statementId && selectedStatementId === statementId ? "is-selected" : ""}`;
              return statementId ? (
                <button
                  key={segment.start}
                  className={className}
                  onClick={() => selectStatement(statementId)}
                  aria-pressed={selectedStatementId === statementId}
                  title={`View ${statementId}: ${title}`}
                >
                  {segment.text}
                </button>
              ) : (
                <span
                  key={segment.start}
                  className={segment.severity ? className : undefined}
                  title={title || undefined}
                >
                  {segment.text}
                </span>
              );
            })}
          </div>
        ) : (
          <textarea
            value={input}
            onChange={(event) => updateInput(event.target.value)}
            disabled={loading}
            aria-label="Article text to analyze"
            aria-describedby="analysis-input-help"
            aria-invalid={characterCount > 40000}
          />
        )}

        <div className="input-bottom">
          <p id="analysis-input-help">
            {characterCount > 40000
              ? "Text exceeds 40,000 characters. Shorten it to analyze."
              : "Paste a document, statement, or post for statement-level feature analysis."}
          </p>
          <button
            className="analyze-button"
            onClick={() => void analyze()}
            disabled={loading || !input.trim() || characterCount > 40000}
          >
            {loading ? "Analyzing…" : "Analyze"} <span>→</span>
          </button>
        </div>
      </div>

      <div className="results-column" ref={resultsColumn}>
        <header className="section-title">
          <span>Results</span>
          <span>
            {loading
              ? "Analyzing"
              : error
                ? "Analysis failed"
                : result
                  ? "Complete"
                  : "Waiting for text"}
          </span>
        </header>

        {loading ? (
          <div className="analysis-loader" role="status" aria-live="polite">
            <span className="analysis-loader-spinner" aria-hidden="true" />
            <p>Analyzing your text…</p>
          </div>
        ) : result ? (
          <>
            <div className="idea">
              <label>Main idea</label>
              <p>
                {result.primary_narrative ?? "No main idea was identified."}
              </p>
            </div>
            <div className="idea">
              <label>Overall assessment</label>
              <p>{result.classification.label.replaceAll("_", " ")}</p>
              <div className="feature-grid overall-feature-grid">
                {features.map((name) => (
                  <Meter
                    key={name}
                    name={name}
                    score={result.features[name]}
                    reason={result.feature_details[name].reason}
                  />
                ))}
              </div>
            </div>
            {result.warnings.length > 0 && (
              <details className="analysis-notice">
                <summary>Analysis notes ({result.warnings.length})</summary>
                <ul>
                  {result.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              </details>
            )}
            <details className="analysis-notice">
              <summary>Analysis details</summary>
              <p>Content ID: {result.material_id}</p>
              <p>Models: {Object.values(result.model_versions).join(", ")}</p>
            </details>
            <div className="results-list">
              {result.statements.map((statement) => (
                <StatementView
                  key={statement.id}
                  statement={statement}
                  selected={selectedStatementId === statement.id}
                  registerElement={(element) => {
                    if (element) resultElements.current[statement.id] = element;
                    else delete resultElements.current[statement.id];
                  }}
                />
              ))}
              {result.statements.length === 0 && (
                <div className="empty">
                  No statement-level findings were returned. Review the analysis
                  notes.
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="empty result-empty" role={error ? "alert" : "status"}>
            <div className="crosshair">+</div>
            <p>
              {error ||
                "Select Analyze to see statement-level findings."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function Briefing() {
  return (
    <section className="screen briefing-screen" id="briefing">
      <header className="briefing-identity">
        <a href="#briefing" aria-label="Veritascope home">
          <span className="briefing-mark" aria-hidden="true">V</span>
          <span>VERITASCOPE</span>
        </a>
      </header>

      <div className="briefing-content">
        <div className="briefing-copy">
          <h1>See how persuasion works <em>and how it spreads.</em></h1>
          <p className="briefing-description">
            Veritascope helps you examine persuasive language and repeated posting patterns. Read the highlighted persuasion tactics, then inspect the posts and timing behind each coordination signal.
          </p>
          <div className="briefing-actions">
            <a className="briefing-primary-cta" href="#analysis">See a statement analyzed <span aria-hidden="true">↓</span></a>
            <a className="briefing-secondary-cta" href="#swarm">See how messages spread</a>
          </div>
        </div>

        <div className="briefing-preview" aria-label="Preview of a fictional content analysis">
          <div className="briefing-preview-topline">
            <span><i /> Example analysis</span>
          </div>
          <div className="briefing-preview-body">
            <p className="briefing-preview-quote">“Anyone questioning the plan is <mark>putting public safety at risk</mark>.”</p>
            <div className="briefing-preview-divider" />
            <div className="briefing-preview-finding">
              <div><strong>Appeal to fear</strong><p>Frames disagreement as a threat to safety.</p></div>
              <span className="briefing-confidence">93%</span>
            </div>
            <div className="briefing-preview-finding briefing-network-finding">
              <div><strong>Repeated across accounts</strong><p>Compare timing and matching activity.</p></div>
              <span className="briefing-network-icon" aria-hidden="true"><i /><i /><i /><i /></span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function App() {
  return (
    <main className="app-shell">
      <Briefing />
      <Analysis />
      <SwarmNetwork />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
