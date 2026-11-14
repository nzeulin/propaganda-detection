/// <reference types="vite/client" />
import { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import SwarmNetwork from "./SwarmNetwork";

type Dimension =
  | "Factual"
  | "Selective"
  | "Emotional"
  | "Logical"
  | "Authority"
  | "Repetition"
  | "Strategic";

type Scores = Record<Dimension, number>;

type Statement = {
  id: string;
  text: string;
  start: number;
  end: number;
  attribution: string;
  stance: string;
  features: Scores;
  technique_spans: TechniqueSpan[];
};

type TechniqueSpan = {
  technique: string;
  confidence: number;
  justification: string;
};

const article =
  "Officials insist the proposal is the only responsible path, despite independent reporting that documents unresolved costs. Anyone questioning the plan is accused of putting public safety at risk. The same warning appeared repeatedly across coordinated accounts before the committee vote.";

const contentAnalysis: {
  content_id: string;
  main_idea: string;
  statements: Statement[];
} = {
  content_id: "CT-441",
  main_idea:
    "A coordinated message frames dissent as a risk to public safety while narrowing the evidence considered.",
  statements: [
    {
      id: "ST-01",
      text: "Officials insist the proposal is the only responsible path, despite independent reporting that documents unresolved costs.",
      start: 0,
      end: 119,
      attribution: "Narrator",
      stance: "asserted",
      features: {
        Factual: 0.38,
        Selective: 0.84,
        Emotional: 0.21,
        Logical: 0.67,
        Authority: 0.73,
        Repetition: 0.18,
        Strategic: 0.76,
      },
      technique_spans: [
        {
          technique: "False dilemma",
          confidence: 0.88,
          justification: "Positions one option as the only responsible path.",
        },
        {
          technique: "Selective presentation",
          confidence: 0.84,
          justification: "Acknowledges but does not engage documented costs.",
        },
      ],
    },
    {
      id: "ST-02",
      text: "Anyone questioning the plan is accused of putting public safety at risk.",
      start: 120,
      end: 193,
      attribution: "Narrator",
      stance: "asserted",
      features: {
        Factual: 0.19,
        Selective: 0.32,
        Emotional: 0.89,
        Logical: 0.72,
        Authority: 0.12,
        Repetition: 0.24,
        Strategic: 0.91,
      },
      technique_spans: [
        {
          technique: "Appeal to fear",
          confidence: 0.93,
          justification: "Links questioning the plan to a threat to safety.",
        },
      ],
    },
    {
      id: "ST-03",
      text: "The same warning appeared repeatedly across coordinated accounts before the committee vote.",
      start: 194,
      end: 286,
      attribution: "Network trace",
      stance: "observed",
      features: {
        Factual: 0.61,
        Selective: 0.18,
        Emotional: 0.23,
        Logical: 0.12,
        Authority: 0.08,
        Repetition: 0.96,
        Strategic: 0.82,
      },
      technique_spans: [
        {
          technique: "Coordinated repetition",
          confidence: 0.96,
          justification:
            "Identical warning amplified across a timed account network.",
        },
      ],
    },
  ],
};

const dimensions = Object.keys(
  contentAnalysis.statements[0].features,
) as Dimension[];

function Meter({ name, score }: { name: Dimension; score: number }) {
  return (
    <div className="meter">
      <div>
        <span>{name}</span>
        <button
          className="info"
          title={`${name} score: observed strength from 0.00 to 1.00.`}
        >
          [i]
        </button>
        <b>{score.toFixed(2)}</b>
      </div>
      <div className="track">
        <i style={{ width: `${score * 100}%` }} />
      </div>
    </div>
  );
}

type StatementViewProps = {
  statement: Statement;
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
          {statement.id} · {statement.attribution.toUpperCase()}
        </span>
        <span>
          {statement.start}—{statement.end}
        </span>
      </header>

      <p className="statement-text">{statement.text}</p>

      <div className="tags">
        {statement.technique_spans.map((span) => (
          <span key={span.technique}>
            {span.technique} <b>{span.confidence.toFixed(2)}</b>
            <em title={span.justification}>[i]</em>
          </span>
        ))}
      </div>

      <div className="feature-grid">
        {dimensions.map((name) => (
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
  const [analyzed, setAnalyzed] = useState(true);
  const [selectedStatementId, setSelectedStatementId] = useState(
    contentAnalysis.statements[0].id,
  );
  const resultElements = useRef<Record<string, HTMLElement | null>>({});

  function updateInput(value: string) {
    setInput(value);
    setAnalyzed(false);
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

  const canHighlightInput = analyzed && input === article;

  return (
    <section className="screen analysis-screen" id="analysis">
      <div className="input-column">
        <header className="section-title">
          <span>02 / NAME THE TECHNIQUE</span>
          <span>CONTENT ANALYSIS</span>
        </header>

        <div className="input-meta">
          <span>CONTENT_ID / {contentAnalysis.content_id}</span>
          <span>{input.length} CHARS</span>
          {analyzed && (
            <button className="edit-input" onClick={() => setAnalyzed(false)}>
              EDIT INPUT
            </button>
          )}
        </div>

        {canHighlightInput ? (
          <div className="input-highlighter" aria-label="Analyzed article text">
            {contentAnalysis.statements.map((statement, index) => (
              <span key={statement.id}>
                <button
                  className={`sentence-highlight highlight-${index + 1} ${selectedStatementId === statement.id ? "is-selected" : ""
                    }`}
                  onClick={() => selectStatement(statement.id)}
                  aria-pressed={selectedStatementId === statement.id}
                  title={`View ${statement.id} analysis`}
                >
                  {statement.text}
                </button>{" "}
              </span>
            ))}
          </div>
        ) : (
          <textarea
            value={input}
            onChange={(event) => updateInput(event.target.value)}
            aria-label="Article text to analyze"
          />
        )}

        <div className="input-bottom">
          <p>
            Paste a document, statement, or post for statement-level feature
            analysis.
          </p>
          <button className="analyze-button" onClick={() => setAnalyzed(true)}>
            ANALYZE <span>→</span>
          </button>
        </div>
      </div>

      <div className="results-column">
        <header className="section-title">
          <span>RESULTS / {analyzed ? "COMPLETE" : "PENDING"}</span>
          <span>MODEL: DEMO-01</span>
        </header>

        {analyzed ? (
          <>
            <div className="idea">
              <label>MAIN IDEA</label>
              <p>{contentAnalysis.main_idea}</p>
            </div>
            <div className="results-list">
              {contentAnalysis.statements.map((statement) => (
                <StatementView
                  key={statement.id}
                  statement={statement}
                  selected={selectedStatementId === statement.id}
                  registerElement={(element) => {
                    resultElements.current[statement.id] = element;
                  }}
                />
              ))}
            </div>
          </>
        ) : (
          <div className="empty result-empty">
            <div className="crosshair">+</div>
            <p>
              Press ANALYZE to generate
              <br />
              statement-level findings
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
        <span className="briefing-identity-note">MEDIA LITERACY / INVESTIGATION TOOLS</span>
      </header>

      <div className="briefing-content">
        <div className="briefing-copy">
          <p className="briefing-index"><span /> UNDERSTAND THE MESSAGE. TRACE THE SPREAD.</p>
          <h1>See how persuasion works <em>and how it spreads.</em></h1>
          <p className="briefing-description">
            Veritascope helps you examine persuasive language and repeated posting patterns. Read the highlighted persuasion tactics, then inspect the posts and timing behind each coordination signal.
          </p>
          <div className="briefing-actions">
            <a className="briefing-primary-cta" href="#analysis">See a statement analyzed <span aria-hidden="true">↓</span></a>
            <a className="briefing-secondary-cta" href="#swarm">See how messages spread</a>
          </div>
          <p className="briefing-trust-note">Investigation signals for people—not automated verdicts.</p>
        </div>

        <div className="briefing-preview" aria-label="Preview of a fictional content analysis">
          <div className="briefing-preview-topline">
            <span><i /> SAMPLE ANALYSIS</span>
            <span>FICTIONAL CONTENT</span>
          </div>
          <div className="briefing-preview-body">
            <div className="briefing-preview-meta"><span>CONTENT / PUBLIC STATEMENT</span><span>03 FINDINGS</span></div>
            <p className="briefing-preview-quote">“Anyone questioning the plan is <mark>putting public safety at risk</mark>.”</p>
            <div className="briefing-preview-divider" />
            <div className="briefing-preview-finding">
              <span className="briefing-finding-index">01</span>
              <div><strong>Appeal to fear</strong><p>Frames disagreement as a threat to safety.</p></div>
              <span className="briefing-confidence">93%</span>
            </div>
            <div className="briefing-preview-finding briefing-network-finding">
              <span className="briefing-finding-index">02</span>
              <div><strong>Repeated across accounts</strong><p>Compare timing and matching activity.</p></div>
              <span className="briefing-network-icon" aria-hidden="true"><i /><i /><i /><i /></span>
            </div>
          </div>
          <div className="briefing-preview-footer"><span>LANGUAGE</span><b /> <span>NETWORK</span><span className="briefing-preview-open">OPEN THE EVIDENCE ↗</span></div>
        </div>
      </div>

      <div className="briefing-bottomline"><span>CONTENT ANALYSIS <b>01</b></span><span>COORDINATION SIGNALS <b>02</b></span><span>HUMAN REVIEW <b>03</b></span></div>
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
