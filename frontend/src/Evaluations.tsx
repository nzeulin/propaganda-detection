import { useEffect, useState } from "react";
import { api, labels, type Feature } from "./types";
import { JobPanel, type Job } from "./JobPanel";

type Metrics = {
  provider_usage: {
    records_with_usage: number;
    input_tokens: number;
    output_tokens: number;
    complete: boolean;
  };
  evaluated: number;
  confusion: Record<string, number>;
  families: Record<
    string,
    {
      tp: number;
      fp: number;
      tn: number;
      fn: number;
      abstained: number;
      precision: number | null;
      recall: number | null;
      f1: number | null;
    }
  >;
  negative_false_positive_rate: number | null;
  abstention_rate: number | null;
  mean_coverage: number | null;
  escalation_rate: number | null;
  mean_seconds: number | null;
  errors: { id: string; reference: string; prediction: string; type: string }[];
  denominators: string;
  reference_type: string;
};
type Summary = {
  corpus: string;
  audit: {
    records: number;
    splits: Record<string, number>;
    labels: { split: string; label: string; count: number }[];
    leakage_checks_pass: boolean;
    exact_duplicates: string[][];
    cross_split_near_duplicates: unknown[];
  };
  metrics: Metrics;
  records: {
    id: string;
    split: string;
    label: string;
    preview: string;
    evaluated: boolean;
  }[];
};
const value = (n: number | null) =>
  n === null ? "Not available" : n.toFixed(3);
export function Evaluations() {
  const [kind, setKind] = useState("synthetic"),
    [split, setSplit] = useState("development"),
    [summary, setSummary] = useState<Summary | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [record, setRecord] = useState<{
      record: {
        text: string;
        reference_annotation: unknown;
        provenance: unknown;
        reference_facts: string;
        comparison_corpus: string;
      };
      prediction: unknown;
    } | null>(null),
    [jobId, setJobId] = useState(""),
    [error, setError] = useState(""),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setSelected([]);
    setRecord(null);
    api<Summary>(
      `/api/v1/evaluation-corpora/${kind}?split=${split}`,
      undefined,
      abort.signal,
    )
      .then(setSummary)
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [kind, split, refresh]);
  async function inspect(id: string) {
    try {
      setRecord(await api(`/api/v1/evaluation-records/${kind}/${id}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function evaluate() {
    try {
      const job = await api<Job>("/api/v1/evaluations", {
        corpus: kind,
        record_ids: selected,
      });
      setJobId(job.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <div className="page-intro">
        <div className="eyebrow">MEASURE, INSPECT, REVISE</div>
        <h1>Evaluation lab.</h1>
        <p>
          Inspect reference annotations, frozen splits and actual application
          predictions. Synthetic and public-source results remain separate.
        </p>
      </div>
      <section className="panel explorer">
        <div className="toolbar">
          <label>
            Corpus{" "}
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="synthetic">Synthetic scenarios</option>
              <option value="web">Public-source excerpts</option>
            </select>
          </label>
          <label>
            Split{" "}
            <select value={split} onChange={(e) => setSplit(e.target.value)}>
              {["development", "validation", "test", "all"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <button className="sample" onClick={() => setRefresh((i) => i + 1)}>
            Refresh metrics
          </button>
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {summary && (
          <>
            <p>
              {summary.audit.records} accepted records ·{" "}
              {summary.metrics.evaluated} evaluated in this selection · leakage
              audit{" "}
              {summary.audit.leakage_checks_pass ? "passed" : "needs review"}
            </p>
            <p className="small muted">
              {summary.metrics.reference_type}. Test records remain held out
              from tuning.
            </p>
            <div className="metric-grid">
              {[
                [
                  "Negative false-positive rate",
                  summary.metrics.negative_false_positive_rate,
                ],
                ["Abstention rate", summary.metrics.abstention_rate],
                ["Mean feature coverage", summary.metrics.mean_coverage],
                ["Deeper-pass rate", summary.metrics.escalation_rate],
                ["Mean analysis seconds", summary.metrics.mean_seconds],
              ].map(([label, n]) => (
                <div className="metric-card" key={label as string}>
                  <small>{label}</small>
                  <strong>{value(n as number | null)}</strong>
                </div>
              ))}
            </div>
            <p className="small muted">
              Provider accounting:{" "}
              {summary.metrics.provider_usage.records_with_usage} records with
              usage ·{" "}
              {summary.metrics.provider_usage.input_tokens.toLocaleString()}{" "}
              input tokens ·{" "}
              {summary.metrics.provider_usage.output_tokens.toLocaleString()}{" "}
              output tokens.{" "}
              {summary.metrics.provider_usage.complete
                ? "Complete for this selection."
                : "Older predictions have incomplete token accounting."}
            </p>
            <h2>Material confusion</h2>
            <div className="confusion-grid">
              {Object.entries(summary.metrics.confusion).map(([label, n]) => (
                <div className="metric-card" key={label}>
                  <small>
                    {
                      {
                        tp: "True positive",
                        fp: "False positive",
                        tn: "True negative",
                        fn: "False negative",
                        abstained: "Abstained",
                      }[label]
                    }
                  </small>
                  <strong>{n}</strong>
                </div>
              ))}
            </div>
            <p className="small muted">{summary.metrics.denominators}</p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Feature family</th>
                    <th>Precision</th>
                    <th>Recall</th>
                    <th>F1</th>
                    <th>TP / FP / FN</th>
                    <th>Abstained</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(summary.metrics.families).map(
                    ([family, m]) => (
                      <tr key={family}>
                        <td>{labels[family as Feature]}</td>
                        <td>{value(m.precision)}</td>
                        <td>{value(m.recall)}</td>
                        <td>{value(m.f1)}</td>
                        <td>
                          {m.tp} / {m.fp} / {m.fn}
                        </td>
                        <td>{m.abstained}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            <details>
              <summary>Split balance and leakage audit</summary>
              <pre>{JSON.stringify(summary.audit, null, 2)}</pre>
            </details>
            <h2>Error drilldown</h2>
            {summary.metrics.errors.length ? (
              summary.metrics.errors.map((e) => (
                <button
                  className="sample"
                  key={e.id}
                  onClick={() => inspect(e.id)}
                >
                  {e.type.replaceAll("_", " ")} · {e.id}
                </button>
              ))
            ) : (
              <p>
                No recorded errors in evaluated cases. Unevaluated cases are not
                counted as successes.
              </p>
            )}
            <h2>Reference materials</h2>
            <div className="toolbar">
              <button
                className="primary"
                disabled={!selected.length}
                onClick={evaluate}
              >
                Evaluate {selected.length} selected records
              </button>
              <span className="small muted">
                Up to ten per resumable job · new predictions use paid APIs
              </span>
            </div>
            <div className="record-list">
              {summary.records.map((r) => (
                <div className="corpus-record" key={r.id}>
                  <input
                    aria-label={`Select ${r.id}`}
                    type="checkbox"
                    checked={selected.includes(r.id)}
                    disabled={!selected.includes(r.id) && selected.length >= 10}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, r.id]
                          : selected.filter((id) => id !== r.id),
                      )
                    }
                  />
                  <button onClick={() => inspect(r.id)}>
                    <strong>
                      {r.label.replaceAll("_", " ")} · {r.split} ·{" "}
                      {r.evaluated ? "evaluated" : "not evaluated"}
                    </strong>
                    <span>{r.preview}</span>
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
      {record && (
        <section className="panel explorer">
          <h2>Material and annotation inspector</h2>
          <p className="article-text">{record.record.text}</p>
          <details open>
            <summary>Independent reference annotation</summary>
            <pre>
              {JSON.stringify(record.record.reference_annotation, null, 2)}
            </pre>
          </details>
          <details>
            <summary>Packaged evidence and provenance</summary>
            <p>{record.record.reference_facts}</p>
            <p>{record.record.comparison_corpus}</p>
            <pre>{JSON.stringify(record.record.provenance, null, 2)}</pre>
          </details>
          <details>
            <summary>Application prediction</summary>
            <pre>{JSON.stringify(record.prediction, null, 2)}</pre>
          </details>
        </section>
      )}
      {jobId && (
        <JobPanel
          id={jobId}
          onChange={setJobId}
          onComplete={() => setRefresh((i) => i + 1)}
        />
      )}
    </>
  );
}
