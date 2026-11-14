import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  api,
  features,
  labels,
  type Analysis,
  type Annotation,
  type Example,
} from "./types";
import { segmentText } from "./highlights";
import "./style.css";

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

function Results({ result }: { result: Analysis }) {
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
            {result.demo ? "OFFLINE SYNTHETIC DEMO" : "LIVE TEXT-ONLY ANALYSIS"}
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

function Analyze() {
  const [mode, setMode] = useState<"text" | "url">("text");
  const [input, setInput] = useState("");
  const [title, setTitle] = useState("");
  const [examples, setExamples] = useState<Example[]>([]);
  const [example, setExample] = useState<string | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [live, setLive] = useState<boolean | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [loading]);
  useEffect(() => {
    const abort = new AbortController();
    api<Example[]>("/examples", undefined, abort.signal)
      .then(setExamples)
      .catch((e) => {
        if (!abort.signal.aborted)
          setError(`Cannot reach the API: ${e.message}`);
      });
    api<{ live_configured: boolean }>("/health", undefined, abort.signal)
      .then((r) => setLive(r.live_configured))
      .catch(() => {});
    return () => {
      abort.abort();
      controller.current?.abort();
    };
  }, []);
  const chooseMode = (next: "text" | "url") => {
    setMode(next);
    setInput("");
    setExample(null);
    setResult(null);
    setError("");
  };
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    controller.current = new AbortController();
    setError("");
    setElapsed(0);
    setLoading(true);
    setResult(null);
    try {
      setResult(
        await api<Analysis>(
          "/analyze",
          {
            ...(example ? { example_id: example } : { [mode]: input }),
            ...(title ? { title } : {}),
            include_details: true,
          },
          controller.current.signal,
        ),
      );
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError"))
        setError(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setLoading(false);
    }
  }
  return (
    <>
      <div className="page-intro">
        <div className="eyebrow">CONTENT INTELLIGENCE / TEXT ONLY</div>
        <h1>
          Read beyond
          <br />
          <span>the narrative.</span>
        </h1>
        <p>
          Explore how a message persuades. Trace every assessed indicator back
          to its words, context and weight.
        </p>
      </div>
      <form className="panel input-panel" onSubmit={submit}>
        <div className="panel-heading">
          <div className="input-tabs" aria-label="Input type">
            <button
              type="button"
              aria-pressed={mode === "text"}
              className={mode === "text" ? "active" : ""}
              disabled={loading}
              onClick={() => chooseMode("text")}
            >
              Paste text
            </button>
            <button
              type="button"
              aria-pressed={mode === "url"}
              className={mode === "url" ? "active" : ""}
              disabled={loading}
              onClick={() => chooseMode("url")}
            >
              Article URL ↗
            </button>
          </div>
          <span className="mono connection">
            <i />
            {live === null
              ? "API CONNECTING"
              : live
                ? "LIVE CONFIGURED"
                : "DEMO READY"}
          </span>
        </div>
        <label className="field-label" htmlFor="article-title-input">
          Title <span className="muted">(optional)</span>
        </label>
        <input
          id="article-title-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Give this analysis a title"
          maxLength={500}
          disabled={loading}
        />
        <label className="field-label" htmlFor="article-input">
          {mode === "text" ? "Article text" : "Public article URL"}
        </label>
        {mode === "text" ? (
          <textarea
            id="article-input"
            placeholder="Paste an article, commentary or speech…"
            value={input}
            disabled={loading}
            onChange={(e) => {
              setInput(Array.from(e.target.value).slice(0, 40000).join(""));
              setExample(null);
            }}
            required
          />
        ) : (
          <input
            id="article-input"
            type="url"
            placeholder="https://example.com/article"
            value={input}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            required
          />
        )}
        <div className="input-footer">
          <span className="small muted">
            {example
              ? "Labeled synthetic sample · no provider calls"
              : mode === "text"
                ? `${Array.from(input).length.toLocaleString()} / 40,000 characters · live providers required`
                : "Readable public HTTP(S) articles · live providers required"}
          </span>
          <button className="primary" disabled={loading || !input.trim()}>
            {loading ? (
              <>
                <span className="spinner" /> Analyzing…
              </>
            ) : (
              <>
                Analyze content <span>↗</span>
              </>
            )}
          </button>
        </div>
        <div className="sample-row">
          <span className="mono muted">TRY A DEMO</span>
          {examples.map((item) => (
            <button
              type="button"
              disabled={loading}
              key={item.id}
              className={`sample ${example === item.id ? "selected" : ""}`}
              onClick={() => {
                setMode("text");
                setInput(item.text);
                setTitle(item.title);
                setExample(item.id);
                setError("");
                setResult(null);
              }}
            >
              {item.title}
              <small>{item.label}</small>
            </button>
          ))}
        </div>
        {loading && (
          <p className="small cyan" role="status">
            Extracting, validating and scoring evidence · {elapsed}s elapsed.
            Live analysis may take several minutes.
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </form>
      <p className="screening-note">
        Experimental manipulation-indicator screening. Scores describe observed
        techniques, not truth or the probability of propaganda.
      </p>
      {result ? (
        <Results result={result} />
      ) : (
        <div className="workflow-teaser">
          <span className="mono cyan">01 / EXTRACT</span>
          <span>→</span>
          <span className="mono">02 / ASSESS</span>
          <span>→</span>
          <span className="mono">03 / TRACE EVIDENCE</span>
        </div>
      )}
    </>
  );
}

function Architecture() {
  const [result, setResult] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    api<Analysis>("/analyze", { example_id: "town-hall" }, abort.signal)
      .then(setResult)
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, []);
  const stages = [
    [
      "Ingestion",
      "Public URL or pasted text. Preserve the source and freeze normalized Unicode text.",
    ],
    [
      "Extraction",
      "Luna extracts narratives, sections, atomic claims, speakers, stances and source spans.",
    ],
    [
      "Validation & grouping",
      "Validate exact excerpts. Group equivalent claims, retaining every occurrence and separate attribution.",
    ],
    [
      "Scoring",
      "Jev assesses relevance and eligible techniques using five descriptive rubric levels, normalized by four.",
    ],
    [
      "Aggregation",
      "Normalize section and within-section importance; publish statement scores at ≥80% coverage.",
    ],
    [
      "Screening",
      "Apply a versioned experimental policy. Missing required dimensions or independent narratives yield inconclusive.",
    ],
  ];
  return (
    <>
      <div className="page-intro">
        <div className="eyebrow">METHOD / EXPLAINABILITY FIRST</div>
        <h1>
          From words
          <br />
          <span>to evidence.</span>
        </h1>
        <p>
          A transparent pipeline. Fixed rubrics, normalized weights and
          explanations you can inspect.
        </p>
      </div>
      <div className="architecture-flow" aria-label="Analysis pipeline">
        {stages.map(([title, description], i) => (
          <section className="panel stage" key={title}>
            <span className="mono cyan">
              0{i + 1} {i < 5 && "→"}
            </span>
            <h2>{title}</h2>
            <p>{description}</p>
          </section>
        ))}
      </div>
      <section className="method-notes">
        <div>
          <div className="eyebrow">THE BASELINE</div>
          <h2>Every claim counts once.</h2>
          <p>
            Section weights sum to one. Within each section, relevance × role
            coefficients normalize to one. Their product gives a claim’s global
            weight. A repeated claim belongs to its earliest valid occurrence’s
            section; every occurrence remains available for repetition and
            highlights.
          </p>
          <div className="formula mono">
            wᵢ = vⱼ × aᵢ|ⱼ
            <br />
            Aₖ = Σ(wᵢ × xᵢ,ₖ) / coverageₖ
            <br />
            Cᵢ,ₖ = wᵢ × xᵢ,ₖ / coverageₖ
          </div>
        </div>
        <div>
          <div className="eyebrow">EVIDENCE BOUNDARIES</div>
          <h2>Missing means unassessed.</h2>
          <p>
            Text alone cannot verify facts or establish what was omitted. Those
            features remain null. Authority scores concern misleading appeals;
            fabricated sources need verification. Rejected or neutrally reported
            quotations do not become the author’s manipulation.
          </p>
          <p>
            The screen requires emotional, logical and strategic assessment.
            Indicators are flagged when at least two assessed dimensions reach
            0.50 and one reaches 0.75. Overall risk stays null. Top-three
            pooling is an optional diagnostic, disabled by default.
          </p>
        </div>
      </section>
      <div className="worked-heading">
        <div className="eyebrow">SYNTHETIC WORKED EXAMPLE</div>
        <h2>A town hall under pressure</h2>
        <p className="muted">
          The same offline pipeline used by Analyze. Fixture scores illustrate
          behavior; they are not a validated model assessment.
        </p>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!result && !error && <p role="status">Loading worked example…</p>}
      {result && (
        <>
          <section className="panel calculation">
            <div className="panel-heading">
              <h2>Canonical claims & exact contributions</h2>
              <span className="mono">EMOTIONAL DIMENSION</span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Claim / stance</th>
                    <th>Section</th>
                    <th>Occurrences</th>
                    <th>rᵢ</th>
                    <th>qᵢ</th>
                    <th>wᵢ</th>
                    <th>xᵢ</th>
                    <th>Cᵢ</th>
                  </tr>
                </thead>
                <tbody>
                  {result.statements.map((claim) => (
                    <tr key={claim.id}>
                      <td>
                        {claim.text}
                        <small>
                          {claim.stance.replaceAll("_", " ")} ·{" "}
                          {claim.role.replaceAll("_", " ")}
                        </small>
                      </td>
                      <td>{claim.section_id}</td>
                      <td>{claim.occurrence_count}</td>
                      <td>{scoreLabel(claim.relevance)}</td>
                      <td>{scoreLabel(claim.role_coefficient)}</td>
                      <td>{scoreLabel(claim.weight)}</td>
                      <td>
                        {scoreLabel(
                          claim.features.emotional_manipulation ?? null,
                        )}
                      </td>
                      <td>
                        {scoreLabel(
                          claim.contributions.emotional_manipulation ?? null,
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">
              Σ wᵢ ={" "}
              {result.statements
                .reduce((sum, c) => sum + (c.weight ?? 0), 0)
                .toFixed(8)}{" "}
              · Coverage ={" "}
              {percent(result.feature_details.emotional_manipulation.coverage)}{" "}
              · Σ Cᵢ ={" "}
              {result.statements
                .reduce(
                  (sum, c) =>
                    sum + (c.contributions.emotional_manipulation ?? 0),
                  0,
                )
                .toFixed(8)}
            </p>
            <p className="small muted">
              Section weights:{" "}
              {result.sections
                .filter((s) => s.weight !== undefined)
                .map((s) => `${s.id} = ${s.weight!.toFixed(4)}`)
                .join(" · ")}
              . Repetition retains both endorsed occurrences; the reported
              accusation is rejected and receives no author highlight.
            </p>
          </section>
          <Results result={result} />
        </>
      )}
    </>
  );
}

function App() {
  const [page, setPage] = useState(
    window.location.hash === "#architecture" ? "architecture" : "analyze",
  );
  useEffect(() => {
    const change = () =>
      setPage(
        window.location.hash === "#architecture" ? "architecture" : "analyze",
      );
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="site-header">
        <a className="brand" href="#analyze">
          <span className="brand-icon">V</span>
          <span>
            VERITAS<span className="cyan">SCOPE</span>
            <small>CONTENT ANALYTICS</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <a
            href="#analyze"
            aria-current={page === "analyze" ? "page" : undefined}
          >
            Analyze
          </a>
          <a
            href="#architecture"
            aria-current={page === "architecture" ? "page" : undefined}
          >
            Architecture & Example
          </a>
        </nav>
        <span className="experimental mono">EXPERIMENTAL / v0.1</span>
      </header>
      <main id="main-content" className="max-w-[1440px] mx-auto px-5 md:px-10">
        {page === "analyze" ? <Analyze /> : <Architecture />}
      </main>
      <footer>
        <span className="mono">VERITAS//ANALYTICS</span>
        <span>
          Evidence before conclusions. Human review remains essential.
        </span>
        <span className="mono cyan">TEXT-ONLY MVP</span>
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
