import "./SystemExplorer.css";
import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "./types";
import { type Job, type Trace } from "./JobPanel";

type Module = {
  id: string;
  label: string;
  description: string;
  provider: string;
  depends_on: string[];
};
export function SystemExplorer() {
  const [modules, setModules] = useState<Module[]>([]);
  const [jobs, setJobs] = useState<
    Pick<Job, "id" | "kind" | "status" | "created_at">[]
  >([]);
  const [jobId, setJobId] = useState(
    () =>
      new URLSearchParams(window.location.hash.split("?")[1]).get("job") || "",
  );
  const [job, setJob] = useState<Job | null>(null);
  const [selected, setSelected] = useState("ingestion");
  const [cursor, setCursor] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [claim, setClaim] = useState("");
  const [signal, setSignal] = useState("");
  const [weight, setWeight] = useState(0.2);
  const [score, setScore] = useState(0.7);
  const [coverage, setCoverage] = useState(0.8);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      api<{ modules: Module[] }>("/api/v1/system", undefined, abort.signal),
      api<typeof jobs>("/api/v1/jobs", undefined, abort.signal),
    ])
      .then(([system, list]) => {
        setModules(system.modules);
        setJobs(list);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, []);
  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setPlaying(false);
    setCursor(-1);
    async function poll() {
      try {
        const value = await api<Job>(
          `/api/v1/jobs/${jobId}`,
          undefined,
          abort.signal,
        );
        setJob(value);
        if (["queued", "running"].includes(value.status))
          timer = setTimeout(poll, 1000);
      } catch (e) {
        if (!abort.signal.aborted) setError((e as Error).message);
      }
    }
    poll();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [jobId]);
  useEffect(() => {
    if (!playing || !job) return;
    const timer = setInterval(
      () =>
        setCursor((i) => {
          if (i >= job.trace.length - 1) {
            setPlaying(false);
            return i;
          }
          return i + 1;
        }),
      1200,
    );
    return () => clearInterval(timer);
  }, [playing, job]);
  const replay = cursor >= 0;
  const visibleTrace = replay
    ? job?.trace.slice(0, cursor + 1) || []
    : job?.trace || [];
  const current = replay ? job?.trace[cursor] : undefined;
  const nodes: Node[] = useMemo(
    () =>
      modules.map((module, index) => {
        const stages = visibleTrace.filter((t) => t.module === module.id);
        const status = stages.at(-1)?.status;
        return {
          id: module.id,
          position: { x: (index % 4) * 260, y: Math.floor(index / 4) * 170 },
          data: {
            label: (
              <div>
                <small>{module.provider}</small>
                <strong>{module.label}</strong>
                <span>{status || "Not run"}</span>
              </div>
            ),
          },
          style: {
            background: current?.module === module.id ? "#164454" : "#101e30",
            color: "#dde6f3",
            border: `1px solid ${status === "completed" ? "#63dce6" : status === "running" ? "#ecc879" : "#30445e"}`,
            width: 220,
            borderRadius: 10,
          },
          ariaLabel: `${module.label}. ${status || "Not run"}. Select to inspect.`,
        };
      }),
    [modules, visibleTrace, current],
  );
  const edges: Edge[] = modules.flatMap((module) =>
    module.depends_on.map((from) => ({
      id: `${from}-${module.id}`,
      source: from,
      target: module.id,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "#52708d" },
    })),
  );
  const active = modules.find((m) => m.id === (current?.module || selected));
  const stages = visibleTrace.filter((t) => t.module === active?.id);
  const claimStages = claim
    ? job?.trace.filter((t) =>
        JSON.stringify(t.artifact).includes(`"${claim}"`),
      )
    : [];
  return (
    <>
      <div className="page-intro">
        <div className="eyebrow">INSIDE THE INVESTIGATION</div>
        <h1>Follow the evidence.</h1>
        <p>
          Explore how source observations become assessments. Select any module
          for its purpose, actual artifacts and timing.
        </p>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <section className="panel explorer">
        <label className="field-label" htmlFor="execution">
          Saved or active execution
        </label>
        <select
          id="execution"
          value={jobId}
          onChange={(e) => {
            setJobId(e.target.value);
            setClaim("");
            setSignal("");
          }}
        >
          <option value="">Explore the system without a run</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>
              {j.kind} · {j.status} · {new Date(j.created_at).toLocaleString()}
            </option>
          ))}
        </select>
        <div className="toolbar">
          <button
            className="sample"
            disabled={!job?.trace.length}
            onClick={() => {
              if (cursor < 0) setCursor(0);
              setPlaying(!playing);
            }}
          >
            {playing ? "Pause replay" : "Play replay"}
          </button>
          <button
            className="sample"
            disabled={!job?.trace.length || cursor <= 0}
            onClick={() => {
              setPlaying(false);
              setCursor((i) => i - 1);
            }}
          >
            Previous stage
          </button>
          <button
            className="sample"
            disabled={!job?.trace.length || cursor >= job.trace.length - 1}
            onClick={() => {
              setPlaying(false);
              setCursor((i) => i + 1);
            }}
          >
            Next stage
          </button>
          <button
            className="sample"
            onClick={() => {
              setPlaying(false);
              setCursor(-1);
            }}
          >
            Reset / live state
          </button>
          <span className="small muted">
            {replay
              ? `Recorded stage ${cursor + 1} / ${job?.trace.length}`
              : job
                ? `Actual execution · ${job.status}`
                : "Module definitions · no simulated execution"}
          </span>
        </div>
        <div className="system-flow">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            onNodeClick={(_, node) => {
              setSelected(node.id);
              setCursor(-1);
              setPlaying(false);
            }}
            nodesDraggable={false}
            colorMode="dark"
          >
            <Background gap={24} color="#21344c" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <label className="field-label" htmlFor="module-select">
          Inspect module
        </label>
        <select
          id="module-select"
          value={active?.id || selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setCursor(-1);
            setPlaying(false);
          }}
        >
          {modules.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
        {active && (
          <div className="module-inspector">
            <div>
              <div className="eyebrow">{active.provider}</div>
              <h2>{active.label}</h2>
              <p>{active.description}</p>
              <p className="small muted">
                Inputs from:{" "}
                {active.depends_on.join(", ") ||
                  "Original material / observed events"}
              </p>
            </div>
            <div>
              {stages.length ? (
                stages.map((s, i) => <Stage key={i} stage={s} />)
              ) : (
                <p>
                  No stage artifact for this module in the selected execution.
                </p>
              )}
            </div>
          </div>
        )}
      </section>
      {job?.kind === "content" && job.result && (
        <section className="panel explorer">
          <h2>Follow a claim</h2>
          <select
            aria-label="Follow a claim"
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
          >
            <option value="">Select a canonical claim</option>
            {job.result.statements.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id}: {c.text.slice(0, 100)}
              </option>
            ))}
          </select>
          {claim && (
            <>
              <p>{job.result.statements.find((c) => c.id === claim)?.text}</p>
              <div className="toolbar">
                {claimStages?.map((s, i) => (
                  <button
                    className="sample"
                    key={i}
                    onClick={() => {
                      setSelected(s.module);
                      setCursor(-1);
                    }}
                  >
                    {s.module.replaceAll("_", " ")}
                  </button>
                ))}
              </div>
              <p>
                {
                  job.result.verification?.checks.find(
                    (c) => c.claim_id === claim,
                  )?.explanation
                }
              </p>
            </>
          )}
        </section>
      )}
      {job?.kind === "swarm" && job.result && (
        <section className="panel explorer">
          <h2>Follow a coordination signal</h2>
          <select
            aria-label="Follow a signal"
            value={signal}
            onChange={(e) => {
              setSignal(e.target.value);
              setSelected("coordination");
            }}
          >
            <option value="">Select a pair</option>
            {job.result.findings.map((f) => (
              <option key={f.id} value={f.id}>
                {f.episode_count} episodes · score {f.score.toFixed(3)} ·{" "}
                {f.id.slice(-12)}
              </option>
            ))}
          </select>
          {signal && (
            <pre>
              {JSON.stringify(
                job.result.findings.find((f) => f.id === signal),
                null,
                2,
              )}
            </pre>
          )}
        </section>
      )}
      <section className="panel explorer">
        <div className="eyebrow">LOCAL FORMULA EXPERIMENT</div>
        <h2>What changes a claim’s contribution?</h2>
        <p>
          Adjust the inputs to the weighted mean. This simulation never changes
          a saved analysis.
        </p>
        <div className="simulator">
          {(
            [
              ["Claim weight", weight, setWeight],
              ["Local severity", score, setScore],
              ["Assessed coverage", coverage, setCoverage],
            ] as const
          ).map(([label, value, setter]) => (
            <label key={label}>
              {label}: {value.toFixed(2)}
              <input
                type="range"
                min="0"
                max="1"
                step=".01"
                value={value}
                onChange={(e) => setter(Number(e.target.value))}
              />
            </label>
          ))}
          <output>
            {coverage > 0 && weight <= coverage
              ? ((weight * score) / coverage).toFixed(4)
              : "Invalid: coverage must include the claim weight and exceed zero"}
            <small>Contribution = weight × severity / assessed coverage</small>
          </output>
        </div>
      </section>
    </>
  );
}
function Stage({ stage }: { stage: Trace }) {
  return (
    <div className="finding">
      <p>
        {stage.status} · {stage.elapsed_seconds.toFixed(3)} seconds ·{" "}
        {stage.provider}
      </p>
      <details>
        <summary>Actual inputs</summary>
        <pre>{JSON.stringify(stage.inputs, null, 2)}</pre>
      </details>
      <details>
        <summary>Saved output artifact</summary>
        <pre>{JSON.stringify(stage.artifact, null, 2)}</pre>
      </details>
    </div>
  );
}
