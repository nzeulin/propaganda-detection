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
  "Several local families have reported rising energy bills, adding to concerns about household costs. " +
  "The Bright Future campaign has highlighted their experiences and presented a plan that it says has support from energy specialists. " +
  "Anyone who opposes this plan is putting corporate profits ahead of our children’s future. " +
  "Organizers say growing public support shows that the town is ready for their approach.";

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
        <strong>{score.value == null ? "Not assessed" : `${Math.round(score.value * 100)}/100`}</strong>
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
      aria-labelledby="analysis-title"
    >
      <header className="analysis-intro">
        <h2 id="analysis-title">Examine how language persuades.</h2>
        <p>
          Analyze a statement, post, or article for possible persuasion techniques. Scores are experimental text indicators; they do not establish truth or intent.
        </p>
      </header>
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
            <span><i /> Text analysis</span>
          </div>
          <div className="briefing-preview-body">
            <div className="briefing-preview-attribution">Statement · author · endorsed</div>
            <p className="briefing-preview-quote">“<mark>Anyone questioning the plan is accused of putting public safety at risk.</mark>”</p>
            <div className="briefing-preview-divider" />
            <div className="briefing-preview-finding">
              <div><strong>Propaganda score</strong><p>Potential fear framing. Inspect the full context and evidence.</p></div>
              <span className="briefing-feature-score">74/100</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ScoringExplanation() {
  const weightedFeatures = [
    ["logical_manipulation", 30],
    ["strategic_persuasion", 30],
    ["emotional_manipulation", 20],
    ["authority_manipulation", 15],
    ["repetition_amplification", 5],
  ] as const;

  return (
    <section className="scoring-explanation" aria-labelledby="scoring-explanation-title">
      <h2 id="scoring-explanation-title">How propaganda detection works</h2>
      <ol className="scoring-schema-steps" aria-label="Detection process">
        <li><span>01</span><div><h3>Submit text</h3><p>An article, statement, or post</p></div></li>
        <li><span>02</span><div><h3>Identify statements</h3><p>AI separates claims, speakers, and stance</p></div></li>
        <li><span>03</span><div><h3>Score indicators</h3><p>Assess signal strength from 0 to 1</p></div></li>
      </ol>

      <div className="scoring-schema-connector" aria-hidden="true">↓</div>
      <p className="scoring-schema-caption">Five indicators · shared weights for text assessment and post screening</p>
      <dl className="scoring-schema-features">
        {weightedFeatures.map(([feature, weight]) => (
          <div key={feature}>
            <dt>{labels[feature]}</dt>
            <dd>{weight}%<span className="scoring-schema-weight" aria-hidden="true"><i style={{ width: `${weight}%` }} /></span></dd>
          </div>
        ))}
      </dl>

      <div className="scoring-schema-connector" aria-hidden="true">↓</div>
      <p className="scoring-schema-caption">Shared weights, separate text and post decisions</p>
      <div className="scoring-schema-outputs">
        <section className="scoring-schema-output" aria-labelledby="schema-text-score">
          <h3 id="schema-text-score">Text score</h3>
          <p className="scoring-schema-formula">Σ(weight × indicator) × 100</p>
          <dl className="scoring-schema-rules">
            <div><dt>50–100</dt><dd>Propaganda</dd></div>
            <div><dt>35–&lt;50</dt><dd>Suspicious</dd></div>
            <div><dt>0–&lt;35</dt><dd>No strong indicators</dd></div>
          </dl>
          <p>These ranges apply to fully assessed scores. Missing indicators are excluded; weights are adjusted and partial results marked. Assessed zeroes count.</p>
          <p>Statement scoring stays separate: emotional, logical, and authority weights of 20:30:10, normalized. Suspicious from 50/100 or any local indicator ≥ 0.50; propaganda from 75/100 with all three assessed.</p>
        </section>
        <section className="scoring-schema-output" aria-labelledby="schema-text-assessment">
          <h3 id="schema-text-assessment">Overall text assessment</h3>
          <p className="scoring-schema-formula">Weighted sum × 100</p>
          <dl className="scoring-schema-rules">
            <div><dt>50–100</dt><dd>Propaganda</dd></div>
            <div><dt>35–&lt;50</dt><dd>Suspicious</dd></div>
            <div><dt>0–&lt;35</dt><dd>No strong text indicators</dd></div>
          </dl>
          <p>Requires emotional, logical, and strategic assessments. Available weights are normalized if optional indicators are missing. Missing required evidence or narrative review → Inconclusive.</p>
        </section>
        <section className="scoring-schema-output" aria-labelledby="schema-post-screening">
          <h3 id="schema-post-screening">Post screening</h3>
          <p className="scoring-schema-formula">Weighted sum × 100</p>
          <dl className="scoring-schema-rules">
            <div><dt>50–100</dt><dd>Propaganda</dd></div>
            <div><dt>35–&lt;50</dt><dd>Requires further analysis</dd></div>
            <div><dt>0–&lt;35</dt><dd>Not propaganda</dd></div>
          </dl>
          <p>Uses the same five weights. Missing post scores count as zero, with no weight adjustment.</p>
        </section>
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
      <ScoringExplanation />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
