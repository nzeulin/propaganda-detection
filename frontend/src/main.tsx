import { useRef, useState } from "react";
import ForceGraph2D, {
  type ForceGraphMethods,
} from "react-force-graph-2d";
import { createRoot } from "react-dom/client";
import "./style.css";

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

type Cluster = {
  cluster_id: string;
  account_ids: string[];
  content_ids: string[];
  risk_score: number;
  evidence: string[];
  events: CoordinatedEvent[];
  links: string[];
};

type CoordinatedEvent = {
  time: string;
  event: string;
};

type GraphNode = {
  id: string;
  label: string;
  kind: "cluster" | "account" | "content";
  cluster?: string;
  risk?: number;
  x?: number;
  y?: number;
};

type GraphLink = {
  source: string;
  target: string;
  cluster: string;
};

const northstarAccounts = [
  "@civic_current",
  "@northstar_report",
  "@signal_desk",
  "@public_eye_02",
];

const northstarContent = ["CT-441", "CT-449", "CT-455"];

const echoAccounts = [
  "@metro_voice",
  "@axis_comment",
  "@watchtower_feed",
];

const echoContent = ["CT-462", "CT-468"];

const graphEdges: [string, string][] = [
  ["@civic_current", "@northstar_report"],
  ["@civic_current", "@signal_desk"],
  ["@signal_desk", "@public_eye_02"],
  ["@civic_current", "CT-441"],
  ["@northstar_report", "CT-449"],
  ["@signal_desk", "CT-455"],
  ["CL-07", "@civic_current"],
  ["CL-07", "CT-441"],
  ["@metro_voice", "@axis_comment"],
  ["@axis_comment", "@watchtower_feed"],
  ["@metro_voice", "CT-462"],
  ["@watchtower_feed", "CT-468"],
  ["CL-12", "@metro_voice"],
  ["CL-12", "CT-462"],
];

const swarmAnalysis: {
  clusters: Cluster[];
  graph: {
    nodes: GraphNode[];
    links: GraphLink[];
  };
} = {
  clusters: [
    {
      cluster_id: "CL-07 / Northstar relay",
      account_ids: northstarAccounts,
      content_ids: northstarContent,
      risk_score: 0.91,
      evidence: [
        "14 posts repeated the same claim in 38 minutes",
        "Four accounts linked to the same shortened URL",
        "Posting cadence began within 71 seconds",
      ],
      events: [
        {
          time: "09:14:02",
          event: "@civic_current publishes CT-441",
        },
        {
          time: "09:15:13",
          event: "@northstar_report repeats key phrase",
        },
        {
          time: "09:21:44",
          event: "three accounts share shortened target",
        },
      ],
      links: [
        "relay-watch.example/brief-44",
        "short.link/k2m",
        "archive.example/CT-441",
      ],
    },
    {
      cluster_id: "CL-12 / Echo depot",
      account_ids: echoAccounts,
      content_ids: echoContent,
      risk_score: 0.74,
      evidence: [
        "Shared image hash detected across three accounts",
        "Two accounts were created within one day",
      ],
      events: [
        {
          time: "11:02:19",
          event: "@metro_voice posts CT-462",
        },
        {
          time: "11:08:57",
          event: "image hash replicated",
        },
      ],
      links: [
        "archive.example/CT-462",
        "media.example/hash-88",
      ],
    },
  ],
  graph: {
    nodes: [
      {
        id: "CL-07",
        label: "CL-07",
        kind: "cluster",
        risk: 0.91,
      },
      {
        id: "CL-12",
        label: "CL-12",
        kind: "cluster",
        risk: 0.74,
      },
      ...northstarAccounts.map((id) => ({
        id,
        label: id,
        kind: "account" as const,
        cluster: "CL-07",
      })),
      ...northstarContent.map((id) => ({
        id,
        label: id,
        kind: "content" as const,
        cluster: "CL-07",
      })),
      ...echoAccounts.map((id) => ({
        id,
        label: id,
        kind: "account" as const,
        cluster: "CL-12",
      })),
      ...echoContent.map((id) => ({
        id,
        label: id,
        kind: "content" as const,
        cluster: "CL-12",
      })),
    ],
    links: graphEdges.map(([source, target]) => ({
      source,
      target,
      cluster: isEchoNode(source) ? "CL-12" : "CL-07",
    })),
  },
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

function isEchoNode(id: string) {
  return (
    id.includes("metro") ||
    id.includes("axis") ||
    id.includes("watchtower") ||
    id === "CL-12"
  );
}

function Inspector({ cluster }: { cluster: Cluster | null }) {
  if (!cluster) {
    return (
      <aside className="inspector">
        <header>
          <span>SWARM INSPECTOR</span>
          <span className="mono">IDLE</span>
        </header>
        <div className="empty">
          <div className="crosshair">+</div>
          <p>
            Select a node to inspect
            <br />
            behavioral clusters
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="inspector">
      <header>
        <span>SWARM INSPECTOR</span>
        <span className="danger">RISK {cluster.risk_score.toFixed(2)}</span>
      </header>
      <div className="inspect-body">
        <h2>{cluster.cluster_id}</h2>
        <div className="timeline">
          {cluster.events.map((item) => (
            <div className="event" key={item.time}>
              <time>{item.time}</time>
              <p>{item.event}</p>
            </div>
          ))}
        </div>
        <section>
          <label>MEMBER ACCOUNTS / {cluster.account_ids.length}</label>
          {cluster.account_ids.map((id) => (
            <div className="data-row" key={id}>
              {id}
            </div>
          ))}
        </section>
        <section>
          <label>SHARED LINKS</label>
          {cluster.links.map((link) => (
            <div className="data-row link" key={link}>
              {link}
            </div>
          ))}
        </section>
      </div>
    </aside>
  );
}

function Network() {
  const graphRef = useRef<
    ForceGraphMethods<GraphNode, GraphLink> | undefined
  >(undefined);
  const [cluster, setCluster] = useState<Cluster | null>(null);

  function inspectNode(node: GraphNode) {
    const clusterId = node.kind === "cluster" ? node.id : node.cluster;
    const matchingCluster = swarmAnalysis.clusters.find((entry) =>
      entry.cluster_id.startsWith(clusterId || ""),
    );

    setCluster(matchingCluster || null);
  }

  function drawNode(node: GraphNode, context: CanvasRenderingContext2D, scale: number) {
    const radius =
      node.kind === "cluster" ? 9 : node.kind === "content" ? 5 : 4;

    context.fillStyle =
      node.kind === "cluster"
        ? "#D32F2F"
        : node.kind === "content"
          ? "#F4EFE6"
          : "#8d8274";
    context.beginPath();
    context.arc(node.x || 0, node.y || 0, radius, 0, 2 * Math.PI);
    context.fill();

    if (scale > 1.25 && node.kind === "cluster") {
      context.fillStyle = "#F4EFE6";
      context.font = `${10 / scale}px monospace`;
      context.fillText(node.label, (node.x || 0) + 12, (node.y || 0) + 4);
    }
  }

  return (
    <section className="screen swarm-screen" id="swarm">
      <div className="graph">
        <ForceGraph2D
          ref={graphRef}
          graphData={swarmAnalysis.graph}
          backgroundColor="#141414"
          nodeRelSize={5}
          cooldownTicks={100}
          enableZoomInteraction={false}
          enablePanInteraction
          onNodeClick={inspectNode}
          linkColor={(link) =>
            link.cluster === "CL-07" ? "#8d2929" : "#633333"
          }
          linkWidth={1}
          nodeCanvasObject={drawNode}
        />
      </div>

      <div className="dataset">
        <label htmlFor="dataset">ACTIVE DATASET</label>
        <select id="dataset" defaultValue="Baltic civic / 48h">
          <option>Baltic civic / 48h</option>
          <option>Election discourse / 7d</option>
          <option>Public health claims / 30d</option>
        </select>
        <p>14,882 accounts · 3,106 content objects</p>
      </div>

      <div className="graph-tools">
        <button
          onClick={() => graphRef.current?.zoom(1.3, 250)}
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          onClick={() => graphRef.current?.zoom(0.77, 250)}
          aria-label="Zoom out"
        >
          −
        </button>
      </div>

      <Inspector cluster={cluster} />

      <a className="analyze-anchor" href="#analysis">
        [ ↓ ANALYZE TEXT ]
      </a>

      <div className="graph-key">
        <span>
          <i className="red-key" /> cluster
        </span>
        <span>
          <i className="cream-key" /> content
        </span>
        <span>
          <i /> account
        </span>
      </div>
    </section>
  );
}

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
        <h1>Explainable Propaganda &amp; Coordinated Manipulation Detection.</h1>
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
      <Network />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
