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
          {statement.id} ·{" "}
          {(statement.speaker_name || statement.speaker)
            .replaceAll("_", " ")
            .toUpperCase()}{" "}
          · {statement.stance.replaceAll("_", " ").toUpperCase()}
        </span>
        <span>
          {statement.source_spans
            .map((span) => `${span.start}—${span.end}`)
            .join(", ")}
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
        <span>REVIEW CONTROL / {review}</span>
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
      resultElements.current[statementId]?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
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
          <span>02 / NAME THE TECHNIQUE</span>
          <span>CONTENT ANALYSIS</span>
        </header>

        <div className="input-meta">
          <span>CONTENT_ID / {result?.material_id ?? "PENDING"}</span>
          <span>{characterCount.toLocaleString()} / 40,000 CHARS</span>
          {result && (
            <button className="edit-input" onClick={() => updateInput(input)}>
              EDIT INPUT
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
            {loading ? "ANALYZING…" : "ANALYZE"} <span>→</span>
          </button>
        </div>
      </div>

      <div className="results-column">
        <header className="section-title">
          <span>
            RESULTS /{" "}
            {loading
              ? "ANALYZING"
              : error
                ? "FAILED"
                : result
                  ? "COMPLETE"
                  : "PENDING"}
          </span>
          <span>
            {result
              ? `MODELS: ${Object.values(result.model_versions).join(" / ")}`
              : "AWAITING ANALYSIS"}
          </span>
        </header>

        {result ? (
          <>
            <div className="idea">
              <label>MAIN IDEA</label>
              <p>
                {result.primary_narrative ?? "No main idea was identified."}
              </p>
            </div>
            <div className="idea">
              <label>MATERIAL-LEVEL FEATURES</label>
              <p>{result.classification.label.replaceAll("_", " ")}</p>
            </div>
            <div className="feature-grid">
              {features.map((name) => (
                <Meter
                  key={name}
                  name={name}
                  score={result.features[name]}
                  reason={result.feature_details[name].reason}
                />
              ))}
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
                (loading
                  ? "Analyzing your text. This may take several minutes."
                  : "Press ANALYZE to generate statement-level findings.")}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function Briefing() {
  function moveToInvestigation() {
    document.getElementById("swarm")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  return (
    <section className="screen briefing-screen" id="briefing">
      <div className="briefing-identity">VERITASCOPE / FIELD BRIEFING</div>

      <div className="briefing-copy">
        <p className="briefing-index">01 / INVESTIGATION INITIALIZATION</p>
        <h1>
          Explainable Propaganda &amp; Coordinated Manipulation Detection.
        </h1>
        <p className="briefing-description">
          An investigation platform analyzing what content says and how networks
          spread it. These are investigation signals, not definitive verdicts.
        </p>
      </div>

      <button className="briefing-scroll-cue" onClick={moveToInvestigation}>
        [ ↓ ]
      </button>
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
