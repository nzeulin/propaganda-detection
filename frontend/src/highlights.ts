import type { Annotation } from "./types";

export interface Segment {
  start: number;
  end: number;
  text: string;
  findings: Annotation[];
  severity: "red" | "yellow" | null;
}

/** Work in Unicode code points so Python offsets remain correct after astral emoji. */
export function segmentText(
  text: string,
  annotations: Annotation[],
  thresholds: { yellow: number; red: number },
): Segment[] {
  const points = Array.from(text);
  const valid = annotations.filter(
    (a) =>
      a.start >= 0 &&
      a.start < a.end &&
      a.end <= points.length &&
      points.slice(a.start, a.end).join("") === a.excerpt &&
      a.attribution === "endorsed" &&
      a.score >= thresholds.yellow,
  );
  const boundaries = [
    ...new Set([0, points.length, ...valid.flatMap((a) => [a.start, a.end])]),
  ].sort((a, b) => a - b);
  return boundaries.slice(0, -1).map((start, i) => {
    const end = boundaries[i + 1];
    const findings = valid.filter((a) => a.start <= start && a.end >= end);
    const strongest = Math.max(0, ...findings.map((a) => a.score));
    return {
      start,
      end,
      text: points.slice(start, end).join(""),
      findings,
      severity: findings.length
        ? strongest >= thresholds.red
          ? "red"
          : "yellow"
        : null,
    };
  });
}
