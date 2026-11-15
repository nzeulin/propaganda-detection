/// <reference types="vite/client" />
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { ImageAnalysisButton } from "./ImageAnalysisButton";
import SwarmNetwork from "./SwarmNetwork";
import {
  api,
  features,
  formatFeatureScore,
  labels,
  type Analysis as AnalysisResult,
  type Claim,
  type Feature,
  type PropagandaScore,
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
        <b>{formatFeatureScore(name, score)}</b>
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

function PropagandaScoreView({ score }: { score: PropagandaScore }) {
  const scoreLabels = {
    not_suspicious: "No strong indicators",
    suspicious: "Suspicious",
    propaganda: "Propaganda",
    requires_review: "Requires review",
    not_assessed: "Not assessed",
  };
  return (
    <section className="propaganda-score" aria-label="Propaganda score">
      <div className="propaganda-score-heading">
        <span title="Experimental weighted indicator score, not a probability. Missing features are excluded; assessed zeroes count.">
          Propaganda score
        </span>
        <strong>{score.value == null ? "Unavailable" : `${Math.round(score.value * 100)}/100`}</strong>
        <span className={`score-label score-${score.label}`}>{scoreLabels[score.label]}</span>
        {score.status === "partial" && <span className="score-partial">Partial</span>}
      </div>
      <p>{score.reason}</p>
    </section>
  );
}

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

      <PropagandaScoreView score={statement.propaganda_score} />
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
  const [statementFilter, setStatementFilter] = useState<"suspicious" | "all" | "unscored">("suspicious");
  const [selectedStatementId, setSelectedStatementId] = useState<string | null>(
    null,
  );
  const controller = useRef<AbortController | null>(null);
  const resultElements = useRef<Record<string, HTMLElement | null>>({});
  const resultsColumn = useRef<HTMLDivElement | null>(null);
  const characterCount = Array.from(input).length;
  const statementGroups = {
    suspicious: result?.statements.filter((statement) =>
      ["suspicious", "propaganda"].includes(statement.propaganda_score.label)) ?? [],
    all: result?.statements ?? [],
    unscored: result?.statements.filter((statement) => statement.propaganda_score.status !== "assessed") ?? [],
  };
  const visibleStatements = statementGroups[statementFilter];

  useEffect(() => () => controller.current?.abort(), []);

  function updateInput(value: string) {
    setInput(value);
    setResult(null);
    setError("");
    setSelectedStatementId(null);
    setStatementFilter("suspicious");
  }

  async function analyze() {
    if (controller.current || !input.trim() || characterCount > 40000) return;
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    setResult(null);
    setError("");
    setSelectedStatementId(null);
    setStatementFilter("suspicious");
    try {
      const response = await api<AnalysisResult>(
        "/analyze",
        { text: input, include_details: true },
        request.signal,
      );
      if (!request.signal.aborted) {
        setResult(response);
        setSelectedStatementId(response.statements.find((statement) =>
          ["suspicious", "propaganda"].includes(statement.propaganda_score.label))?.id ?? null);
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
    if (!visibleStatements.some((statement) => statement.id === statementId)) setStatementFilter("all");
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

  function changeFilter(filter: typeof statementFilter) {
    setStatementFilter(filter);
    setSelectedStatementId((current) =>
      statementGroups[filter].some((statement) => statement.id === current)
        ? current : statementGroups[filter][0]?.id ?? null);
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
          <ImageAnalysisButton />
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
            <PropagandaScoreView score={result.propaganda_score} />
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
            <div className="statement-filters" role="group" aria-label="Statement filters">
              {([
                ["suspicious", "Suspicious"],
                ["all", "All statements"],
                ["unscored", "Unscored / partial"],
              ] as const).map(([filter, label]) => (
                <button type="button" key={filter} aria-pressed={statementFilter === filter}
                  onClick={() => changeFilter(filter)}>{label} ({statementGroups[filter].length})</button>
              ))}
            </div>
            <div className="results-list">
              {visibleStatements.map((statement) => (
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
              {visibleStatements.length === 0 && (
                <div className="empty">
                  {result.statements.length === 0
                    ? "No statement-level findings were returned. Review the analysis notes."
                    : statementFilter === "suspicious"
                      ? "No suspicious statements found in the assessed evidence. Use All statements or Unscored / partial to inspect the rest."
                      : "No unscored or partially assessed statements."}
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

function ScoringExplanation() {
  return (
    <section className="scoring-explanation" aria-labelledby="scoring-explanation-title">
      <h2 id="scoring-explanation-title">How propaganda detection works</h2>
      <div className="scoring-explanation-grid">
        <div>
          <h3>Detecting persuasion</h3>
          <p>
            AI identifies statements and persuasion techniques, then scores emotional
            pressure, misleading logic, misleading appeals to authority, repetition
            within the text, and strategic persuasion from 0 to 1. Statement-level
            scoring considers claims attributed to and endorsed by the author;
            repetition and strategy are assessed across the whole text.
          </p>
        </div>
        <div>
          <h3>Calculating text scores</h3>
          <p>
            The experimental score out of 100 combines logical and strategic
            indicators at 30% each, emotional indicators at 20%, and authority and
            repetition at 10% each. Statement scores use only emotional, logical,
            and authority indicators. Missing assessments are excluded and the
            remaining weights adjusted; assessed zeroes count. Partial results are
            marked. Scores describe signal strength, not probability.
          </p>
        </div>
        <div>
          <h3>Reading detection labels</h3>
          <p>
            With required assessments available, the overall text assessment flags
            indicators when two or more dimensions reach 0.50 and at least one
            reaches 0.75. Post screening uses a separate rule: two dimensions at
            0.75 or above trigger “Propaganda”; otherwise, any dimension at 0.50 or
            above triggers “Requires further analysis”. Lower scores receive “Not
            propaganda”. Missing post scores currently count as zero.
          </p>
        </div>
      </div>
      <p className="scoring-explanation-note">
        Text analysis does not independently verify facts or establish intent.
      </p>
    </section>
  );
}

function App() {
  return (
    <main className="app-shell">
      <Briefing />
      <Analysis />
      <SwarmNetwork />
      <ScoringExplanation />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
