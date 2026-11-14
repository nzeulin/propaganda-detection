export const features = [
  "factual_manipulation",
  "selective_presentation",
  "emotional_manipulation",
  "logical_manipulation",
  "authority_manipulation",
  "repetition_amplification",
  "strategic_persuasion",
] as const;
export type Feature = (typeof features)[number];
export const labels: Record<Feature, string> = {
  factual_manipulation: "Factual manipulation",
  selective_presentation: "Selective presentation",
  emotional_manipulation: "Emotional manipulation",
  logical_manipulation: "Logical manipulation",
  authority_manipulation: "Authority manipulation",
  repetition_amplification: "Repetition & amplification",
  strategic_persuasion: "Strategic persuasion",
};
export interface Assessment {
  raw_score: number;
  probabilities: number[];
  confidence: number;
  model: string;
}
export interface Annotation {
  id: string;
  start: number;
  end: number;
  excerpt: string;
  feature: Feature;
  score: number;
  claim_id: string | null;
  attribution: string;
  speaker: string;
  speaker_name: string | null;
  contribution: number | null;
  contribution_scope: string;
  rubric: string[];
  assessment: Assessment;
}
export interface Claim {
  id: string;
  text: string;
  section_id: string;
  role: string;
  stance: string;
  speaker: string;
  relevance: number | null;
  role_coefficient: number | null;
  local_weight: number | null;
  weight: number | null;
  occurrence_count: number;
  features: Partial<Record<Feature, number | null>>;
  contributions: Partial<Record<Feature, number>>;
}
export interface Analysis {
  material_id: string;
  title: string | null;
  normalized_text: string;
  demo: boolean;
  primary_narrative: string | null;
  review_required: boolean;
  features: Record<Feature, number | null>;
  feature_details: Record<
    Feature,
    { status: string; coverage: number; reason: string; scope: string }
  >;
  classification: {
    label: string;
    policy_version: string;
    trigger_features: Feature[];
  };
  sections: {
    id: string;
    title: string;
    weight?: number;
    relevance?: number;
  }[];
  statements: Claim[];
  annotations: Annotation[];
  warnings: string[];
  provenance: { content_sha256: string; aggregation: string };
  model_versions: Record<string, string>;
  versions: Record<string, string>;
  highlight_thresholds: { yellow: number; red: number };
}
export interface Example {
  id: string;
  title: string;
  label: string;
  text: string;
}

export async function api<T>(
  path: string,
  body?: object,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    ...(body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
    signal,
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((v: { msg: string }) => v.msg).join(" · ")
          : "Request failed. Try again.",
    );
  }
  return data;
}
