"""Typed extraction and public input contracts; offsets count Unicode code points."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(Entity):
    text: str | None = Field(default=None, min_length=1, max_length=40000)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    example_id: str | None = None
    title: str | None = Field(default=None, max_length=500)
    mode: Literal["text_only"] = "text_only"
    include_details: bool = True

    @model_validator(mode="after")
    def one_input(self):
        if sum(value is not None for value in (self.text, self.url, self.example_id)) != 1:
            raise ValueError("Supply exactly one of text, url, or example_id.")
        if self.text is not None and not self.text.strip():
            raise ValueError("Paste readable article text.")
        return self


class SourceExcerpt(Entity):
    paragraph_id: str
    excerpt: str


class Span(SourceExcerpt):
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class Narrative(Entity):
    id: str
    summary: str
    kind: Literal["argumentative", "informational"]


class Section(Entity):
    id: str
    title: str
    paragraph_ids: list[str]


class TechniqueFinding(Entity):
    technique: Literal[
        "loaded_language",
        "appeal_to_fear",
        "false_dilemma",
        "scapegoating",
        "ad_hominem",
        "appeal_to_authority",
        "bandwagon",
        "repetition",
        "thought_terminating_cliche",
        "coercive_identity",
        "misleading_statistics",
        "unsupported_factual_assertion",
        "cherry_picking",
    ]
    excerpt: str
    explanation: str


class StatementContent(Entity):
    id: str
    canonical_claim_id: str
    text: str
    section_id: str
    narrative_id: str
    role: Literal["main_conclusion", "supporting_claim", "counterargument", "background", "other"]
    speaker: Literal["author", "named_source", "unnamed_source", "other"]
    speaker_name: str | None
    stance: Literal["endorsed", "rejected", "neutrally_reported", "unclear"]
    is_direct_quote: bool
    author_attributable: bool
    techniques: list[TechniqueFinding] = Field(default_factory=list)


class Statement(StatementContent):
    source_spans: list[Span]
    context_excerpt: str


class Pattern(Entity):
    feature: Literal["repetition_amplification", "strategic_persuasion"]
    description: str
    statement_ids: list[str]


class Extraction(Entity):
    narratives: list[Narrative]
    sections: list[Section]
    statements: list[Statement]
    patterns: list[Pattern]


class Assessment(Entity):
    raw_score: float = Field(ge=0, le=4)
    probabilities: list[float] = Field(min_length=5, max_length=5)
    confidence: float = Field(ge=0, le=1)
    model: str

    @model_validator(mode="after")
    def valid_distribution(self):
        if any(not 0 <= p <= 1 for p in self.probabilities) or abs(sum(self.probabilities) - 1) > 1e-5:
            raise ValueError("Invalid rubric distribution")
        return self

    @property
    def score(self):
        return self.raw_score / 4


class FeatureVector(Entity):
    factual_manipulation: float | None = Field(ge=0, le=1)
    selective_presentation: float | None = Field(ge=0, le=1)
    emotional_manipulation: float | None = Field(ge=0, le=1)
    logical_manipulation: float | None = Field(ge=0, le=1)
    authority_manipulation: float | None = Field(ge=0, le=1)
    repetition_amplification: float | None = Field(ge=0, le=1)
    strategic_persuasion: float | None = Field(ge=0, le=1)


class FeatureDetail(Entity):
    status: Literal["assessed", "not_assessed"]
    coverage: float = Field(ge=0, le=1 + 1e-8)
    reason: str
    scope: Literal["text_only", "within_material", "external_evidence"]
    assessment: Assessment | None


class Classification(Entity):
    mode: Literal["text_only"]
    label: Literal["suspicious", "propaganda", "indicators_detected", "no_strong_text_indicators", "inconclusive"]
    weighted_score: float | None = Field(default=None, ge=0, le=1)
    risk_score: None
    policy_version: str
    experimental: Literal[True]
    trigger_features: list[str]
    strong_features: list[str]


class PropagandaScore(Entity):
    value: float | None = Field(ge=0, le=1)
    status: Literal["assessed", "partial", "not_assessed"]
    label: Literal["not_suspicious", "suspicious", "propaganda", "requires_review", "not_assessed"]
    reason: str
    policy_version: str


class ScoredStatement(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    propaganda_score: PropagandaScore


class AnalysisResponse(Entity):
    material_id: str
    title: str | None
    original_text: str
    normalized_text: str
    paragraphs: list[dict]
    source_url: str | None
    original_url: str | None
    mode: Literal["text_only"]
    demo: bool
    primary_narrative: str | None
    narratives: list[Narrative]
    review_required: bool
    features: FeatureVector
    availability: dict[str, bool]
    availability_mask: list[bool] = Field(min_length=7, max_length=7)
    coverage: dict[str, float]
    feature_details: dict[str, FeatureDetail]
    classification: Classification
    propaganda_score: PropagandaScore
    sections: list[dict] | None = None
    statements: list[ScoredStatement] | None = None
    contextual_findings: list[dict] | None = None
    annotations: list[dict] | None = None
    diagnostics: dict | None = None
    warnings: list[str]
    model_versions: dict[str, str]
    versions: dict[str, str]
    provenance: dict
    highlight_thresholds: dict[str, float]
    verification: dict | None = None
    investigation_status: str | None = None
    provider_usage: list[dict] = Field(default_factory=list)
