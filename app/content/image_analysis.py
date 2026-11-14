"""Image observations, evidence and caption attribution for a standalone analysis."""

from typing import Literal

from pydantic import Field

from app.content.schemas import Entity

TextStatus = Literal["readable", "partially_readable", "unreadable", "no_visible_text"]
ReportStatus = Literal["signals_found", "needs_context", "no_clear_signals"]


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
    status: ReportStatus


class ImageFindingCheck(Entity):
    candidate_index: int = Field(ge=0, lt=5)
    decision: Literal["supported", "unsupported", "needs_context"]
    alternative_explanation: str
    reason: str
    visible_quotes: list[str] = Field(max_length=4)


class ImageEvidenceReview(Entity):
    findings: list[ImageFindingCheck] = Field(max_length=5)
    caption_assessment: CaptionAssessment


def _anchor_caption(assessment: CaptionAssessment, caption: str) -> CaptionAssessment:
    if not caption:
        return CaptionAssessment(stance="not_provided", excerpt=None)
    if (
        assessment.stance in {"not_provided", "unclear"}
        or not assessment.excerpt
        or not assessment.excerpt.strip()
        or assessment.excerpt not in caption
    ):
        return CaptionAssessment(stance="unclear", excerpt=None)
    return assessment


def _report_status(findings: list[ImageFinding], context_needed: str | None) -> ReportStatus:
    if findings:
        return "signals_found"
    if context_needed:
        return "needs_context"
    return "no_clear_signals"


def assess_image(observation: ImageObservation, caption: str, model: str) -> ImageAnalysisReport:
    text_status = observation.text_status
    image_text = observation.image_text.strip()
    if text_status in {"unreadable", "no_visible_text"}:
        image_text = ""
    elif not image_text:
        text_status = "unreadable"

    caption_assessment = _anchor_caption(observation.caption_assessment, caption)

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
    return ImageAnalysisReport(
        description=observation.description,
        image_text=image_text,
        text_status=text_status,
        caption_assessment=caption_assessment,
        findings=findings,
        context_needed=context_needed,
        model=model,
        status=_report_status(findings, context_needed),
    )


def apply_image_review(
    report: ImageAnalysisReport, review: ImageEvidenceReview | None, caption: str
) -> ImageAnalysisReport:
    checks = {check.candidate_index: check for check in review.findings} if review else {}
    if review and (len(checks) != len(review.findings) or any(i >= len(report.findings) for i in checks)):
        review = None
        checks.clear()

    notes = [report.context_needed] if report.context_needed else []
    findings = []
    if review is None:
        notes.append("The evidence review could not finish. Unverified findings are withheld.")
    else:
        for index, finding in enumerate(report.findings):
            check = checks.get(index)
            if not check or not check.alternative_explanation.strip() or not check.reason.strip():
                notes.append("The evidence review did not resolve every possible finding.")
            elif check.decision == "supported":
                if any(
                    item.source == "image_text" and item.excerpt not in check.visible_quotes
                    for item in finding.evidence
                ):
                    notes.append("The evidence review could not confirm the quoted wording in the image.")
                else:
                    findings.append(finding)
            elif check.decision == "needs_context":
                notes.append(check.reason.strip())

    caption_assessment = report.caption_assessment
    if caption_assessment.stance not in {"not_provided", "unclear"}:
        checked = _anchor_caption(review.caption_assessment, caption) if review else None
        if checked is not None and checked.stance == caption_assessment.stance:
            caption_assessment = checked
        else:
            caption_assessment = CaptionAssessment(stance="unclear", excerpt=None)
            notes.append("The available caption evidence did not settle how the author frames the image.")

    context_needed = " ".join(dict.fromkeys(notes)) or None
    return report.model_copy(
        update={
            "findings": findings,
            "caption_assessment": caption_assessment,
            "context_needed": context_needed,
            "status": _report_status(findings, context_needed),
        }
    )
