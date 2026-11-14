"""Image observations, evidence and caption attribution for a standalone analysis."""

from typing import Literal

from pydantic import Field

from app.content.schemas import Entity

TextStatus = Literal["readable", "partially_readable", "unreadable", "no_visible_text"]


class ImageEvidence(Entity):
    source: Literal["image_text", "visual", "caption"]
    excerpt: str


class ImageFinding(Entity):
    technique: Literal[
        "appeal_to_fear",
        "loaded_language",
        "scapegoating",
        "dehumanization",
        "false_dilemma",
        "appeal_to_authority",
        "coercive_identity",
        "misleading_visual_scale",
    ]
    explanation: str
    evidence: list[ImageEvidence] = Field(min_length=1, max_length=4)


class CaptionAssessment(Entity):
    stance: Literal["endorsed", "rejected", "neutrally_reported", "unclear", "not_provided"]
    excerpt: str | None


class ImageObservation(Entity):
    description: str
    image_text: str
    text_status: TextStatus
    caption_assessment: CaptionAssessment
    findings: list[ImageFinding] = Field(max_length=5)
    context_needed: str | None


class ImageAnalysisReport(ImageObservation):
    model: str
    status: Literal["signals_found", "needs_context", "no_clear_signals"]


def assess_image(observation: ImageObservation, caption: str, model: str) -> ImageAnalysisReport:
    text_status = observation.text_status
    image_text = observation.image_text.strip()
    if text_status in {"unreadable", "no_visible_text"}:
        image_text = ""
    elif not image_text:
        text_status = "unreadable"

    caption_assessment = observation.caption_assessment
    if not caption:
        caption_assessment = CaptionAssessment(stance="not_provided", excerpt=None)
    elif (
        caption_assessment.stance in {"not_provided", "unclear"}
        or not caption_assessment.excerpt
        or not caption_assessment.excerpt.strip()
        or caption_assessment.excerpt not in caption
    ):
        caption_assessment = CaptionAssessment(stance="unclear", excerpt=None)

    findings = []
    sources = {"image_text": image_text, "caption": caption}
    for finding in observation.findings:
        attachment = any(item.source != "caption" for item in finding.evidence)
        grounded = all(
            item.excerpt.strip() and (item.source == "visual" or item.excerpt in sources[item.source])
            for item in finding.evidence
        )
        if attachment and grounded and finding.explanation.strip():
            findings.append(finding)

    context_needed = (observation.context_needed or "").strip() or None
    if context_needed is None:
        if len(findings) != len(observation.findings):
            context_needed = "Some proposed findings lacked usable evidence in the image or caption."
        elif text_status in {"partially_readable", "unreadable"}:
            context_needed = "Some image text could not be read. A clearer image could help."
        elif caption_assessment.stance == "unclear":
            context_needed = "The post caption does not settle how its author frames the image."
    if findings:
        status = "signals_found"
    elif context_needed:
        status = "needs_context"
    else:
        status = "no_clear_signals"
    return ImageAnalysisReport(
        description=observation.description,
        image_text=image_text,
        text_status=text_status,
        caption_assessment=caption_assessment,
        findings=findings,
        context_needed=context_needed,
        model=model,
        status=status,
    )
