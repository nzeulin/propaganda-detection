"""A conservative, local second pass over existing text highlights."""

import re
from bisect import bisect_right
from collections import defaultdict
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.content.schemas import Entity


class Excerpt(Entity):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    excerpt: str = Field(min_length=1, max_length=40000)


class CandidateHighlight(Excerpt):
    # Accept original analysis annotations, which also contain rubric and score fields.
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=200)


class AttributionReviewInput(Entity):
    normalized_text: str = Field(min_length=1, max_length=40000)
    annotations: list[CandidateHighlight] = Field(max_length=5000)

    @model_validator(mode="after")
    def anchor_highlights(self):
        seen = set()
        for highlight in self.annotations:
            if highlight.id in seen:
                raise ValueError(f"Duplicate annotation ID: {highlight.id}")
            seen.add(highlight.id)
            if (
                not 0 <= highlight.start < highlight.end <= len(self.normalized_text)
                or not highlight.excerpt.strip()
                or self.normalized_text[highlight.start : highlight.end] != highlight.excerpt
            ):
                raise ValueError(f"Annotation {highlight.id} must match the text at its Unicode offsets")
        return self


Decision = Literal["keep", "exclude", "needs_review"]


class ContextReview(Entity):
    decision: Decision
    reason: str
    evidence: list[Excerpt] = Field(default_factory=list)


class PassageReview(ContextReview):
    annotation_ids: list[str]
    passage: Excerpt


class AttributionReviewReport(Entity):
    passages: list[PassageReview]
    kept_annotation_ids: list[str]


# Rules are deliberately limited to explicit English frames attached to a passage.
# Quotes, a reporting verb, and a nearby reaction carry different evidence.
_QUOTATIONS = re.compile(
    r"""“[^“”]+”|„[^„“]+“|«[^«»]+»|‘(?:[^‘’]|(?<=\w)’(?=\w))+’"""
    r"""|(?<!\w)"[^"\n]+"|(?<!\w)'(?:[^'\n]|(?<=\w)'(?=\w))+'(?!\w)"""
)
_OPEN_QUOTE = re.compile(r"""(?<!\w)(?P<cue>[“„«‘"'])""")
_SENTENCE_BREAK = re.compile(r"[.!?;\n]")
_WORD = r"[^\W\d_][\w’'-]*"
_SPEECH_VERB = r"(?:said|wrote|stated|claimed|told\s+[\w’-]+|posted|argued|reported|testified|remarked)"
_FIRST_PERSON = r"(?:I|we)"
_REPORTING_END = r"(?=[ \t]*(?:[.!?;\n]|$))"
_SELF_PRE = re.compile(rf"^\s*(?P<cue>{_FIRST_PERSON}\s+{_SPEECH_VERB})[ \t,:]*$", re.IGNORECASE)
_SELF_POST = re.compile(rf"^[\s,]*(?P<cue>{_FIRST_PERSON}\s+{_SPEECH_VERB}){_REPORTING_END}", re.IGNORECASE)
_SPEAKER = rf"""(?:
    (?:the|a)(?:[ \t]+(?!{_SPEECH_VERB}\b|and\b|but\b|that\b){_WORD}){{1,5}}
    |he|she|they
    |(?!I\b|we\b|you\b)(?:(?:Dr|Mr|Mrs|Ms|Prof)\.[ \t]+)?
      (?-i:[A-Z][\w’'-]*(?:[ \t]+[A-Z][\w’'-]*){{0,4}})
)"""
_PRE_REPORT = re.compile(
    rf"""^\s*(?P<cue>
        according\s+to\s+{_SPEAKER}\s*,
        |{_SPEAKER}\s+{_SPEECH_VERB}(?:\s+that\b)?[ \t,:]*
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)
_POST_REPORT = re.compile(
    rf"""^[\s,]*(?P<cue>{_SPEAKER}\s+{_SPEECH_VERB}|{_SPEECH_VERB}\s+{_SPEAKER})
        {_REPORTING_END}""",
    re.IGNORECASE | re.VERBOSE,
)
_AUTHOR = r"(?:I|we|(?:this|the)\s+(?:author|reporter|writer|post|article|editorial))"
_REFERENCE = r"(?:it|(?:that|this)\s+(?:claim|statement|quote|accusation|allegation|argument|label|rhetoric))"
_STANCE = rf"""(?:
    (?P<rejects>
        {_AUTHOR}\s+(?:reject(?:s|ed)?|disput(?:e[sd]?)|refut(?:e[sd]?)|retract(?:s|ed)?
          |withdraws?|withdrew|disagree(?:s|d)?\s+with
          |(?:do|does)\s+not\s+endorse)\s+(?:{_REFERENCE}|the\s+following\s+claim)
        |(?:I|we)\s+(?:disagree|(?:do\s+not|don['’]t)\s+agree)(?:\s+with\s+{_REFERENCE})?
        |(?:that|this)(?:\s+(?:claim|statement|accusation|allegation|label))?\s+(?:is|was)
          \s+(?:false|misleading|wrong|baseless|unfounded)
    )
    |(?P<endorses>
        {_AUTHOR}\s+(?:endorse[sd]?|believe[sd]?|stands?\s+by)\s+(?:{_REFERENCE}|the\s+following\s+claim)
        |(?:I|we)\s+agree(?:\s+with\s+{_REFERENCE})?
        |(?:that|this)(?:\s+(?:claim|statement|accusation|allegation))?\s+(?:is|was)
          \s+(?:true|correct|right)
        |(?:he|she)(?:\s+is|['’]s)\s+right|they\s+are\s+right
    )
)"""
_PRE_STANCE = re.compile(rf"^\s*{_STANCE}[ \t,:—–-]*$", re.IGNORECASE | re.VERBOSE)
_POST_STANCE = re.compile(
    rf"^[\s,.!?;:—–-]*(?:(?:and|but|however)\b[\s,]+)?{_STANCE}"
    r"(?=[ \t]*(?:[.!;\n](?!\?)|$))",
    re.IGNORECASE | re.VERBOSE,
)
_EXAMPLE = re.compile(
    r"^\s*(?P<cue>(?:(?:this|the following) is )?(?:an )?example of "
    r"(?:loaded language|a fear appeal|a false dilemma|an ad hominem attack|scapegoating)"
    r"|suppose (?:someone|a speaker) (?:says|claims|argues))[ \t,:—–-]*$",
    re.IGNORECASE,
)
_TRANSCRIPT_CUE = re.compile(r"[ \t]*(?:>[ \t]*|[A-Z][A-Z0-9 \t]{1,30}:[ \t]*)")
_ABBREVIATION = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof)$", re.IGNORECASE)
_CONTEXT_LIMIT = 360


def _punctuation_only(value):
    return all(character.isspace() or character in ".,!?;:—–-" for character in value)


def _span(text, start, end):
    return Excerpt(start=start, end=end, excerpt=text[start:end])


def _evidence(text, offset, match, group):
    start, end = match.span(group)
    while end > start and text[offset + end - 1].isspace():
        end -= 1
    return _span(text, offset + start, offset + end)


def _review_passage(text, passage, quotes, quote_ends, paragraph_breaks):
    start, end = passage.start, passage.end
    index = bisect_right(quote_ends, start)
    quote = quotes[index] if index < len(quotes) and quotes[index].start() < end else None
    if quote:
        if not _punctuation_only(text[start : max(start, quote.start())] + text[min(end, quote.end()) : end]):
            return ContextReview(
                decision="needs_review",
                reason="The highlight includes a quotation and other wording. Check each speaker separately.",
                evidence=[_span(text, quote.start(), quote.end())],
            )
        start, end = quote.span()

    prior_quote_end = quote_ends[index - 1] if index else 0
    left_start = max(0, start - _CONTEXT_LIMIT, prior_quote_end)
    left_window = text[left_start:start]
    boundary_at = 0
    for boundary in _SENTENCE_BREAK.finditer(left_window):
        if boundary.group() == "." and _ABBREVIATION.search(left_window[: boundary.start()]):
            continue
        boundary_at = boundary.end()
    left_start += boundary_at
    left = text[left_start:start]
    pre_report = _PRE_REPORT.match(left)
    next_index = index + int(quote is not None)
    next_quote = quotes[next_index].start() if next_index < len(quotes) else len(text)
    right_end = min(next_quote, end + _CONTEXT_LIMIT, len(text))
    # Reactions belong to the same paragraph, or its first follow-up paragraph
    # when the quotation occupies a paragraph of its own.
    paragraph_index = bisect_right(paragraph_breaks, end - 1)
    paragraph_end = (
        paragraph_breaks[paragraph_index] if paragraph_index < len(paragraph_breaks) else len(text)
    )
    if not _punctuation_only(text[end : min(right_end, paragraph_end)]):
        right_end = min(right_end, paragraph_end)
    elif paragraph_index + 1 < len(paragraph_breaks):
        right_end = min(right_end, paragraph_breaks[paragraph_index + 1])
    right = text[end:right_end]
    # A suffix reporting clause belongs to a direct quote. For unquoted text,
    # use an adjacent reporting prefix or an explicit stance tied to that prefix.
    post_report = _POST_REPORT.match(right) if quote else None
    pre_self = _SELF_PRE.match(left) if quote else None
    post_self = _SELF_POST.match(right) if quote else None
    reporting = []
    if pre_report:
        reporting.append(_evidence(text, left_start, pre_report, "cue"))
    if post_report:
        reporting.append(_evidence(text, end, post_report, "cue"))
    if not quote and pre_report and _SENTENCE_BREAK.search(passage.excerpt.strip().rstrip(".!?;")):
        return ContextReview(
            decision="needs_review",
            reason="The unquoted highlight spans several clauses. Check where the other speaker's words end.",
            evidence=reporting,
        )

    example = _EXAMPLE.match(left) if quote else None
    if not quote:
        opening = _OPEN_QUOTE.search(text, max(prior_quote_end, start - _CONTEXT_LIMIT), start)
        if opening:
            return ContextReview(
                decision="needs_review",
                reason="An opening quotation mark has no matching close near the passage.",
                evidence=[_evidence(text, 0, opening, "cue")],
            )
    if not (quote or reporting):
        if _TRANSCRIPT_CUE.fullmatch(left):
            return ContextReview(
                decision="needs_review",
                reason="The passage starts a block quote or a speaker turn with no settled author stance.",
                evidence=[_span(text, left_start, start)],
            )
        return ContextReview(
            decision="keep",
            reason="No local quotation or reporting frame was found for this highlight.",
        )

    stances = defaultdict(list)
    before = _PRE_STANCE.match(left)
    if before:
        stances[before.lastgroup].append(_evidence(text, left_start, before, before.lastgroup))
    reporting_suffix = post_report or post_self
    after_start = end + (reporting_suffix.end() if reporting_suffix else 0)
    reaction = text[after_start:right_end]
    # Only consider consecutive, explicit reactions to this passage.
    for _ in range(2):
        after = _POST_STANCE.match(reaction)
        if not after:
            break
        stances[after.lastgroup].append(_evidence(text, after_start, after, after.lastgroup))
        after_start += after.end()
        reaction = reaction[after.end() :]

    # A clipped window can miss the qualification of an otherwise explicit cue.
    if right_end < len(text) and (
        right_end == end + _CONTEXT_LIMIT or (after_start == right_end and text[right_end] not in ".!;\n")
    ):
        return ContextReview(
            decision="needs_review",
            reason="The reaction continues beyond the inspected passage.",
            evidence=stances["endorses"] + stances["rejects"] or reporting,
        )
    if stances["endorses"] and (stances["rejects"] or example):
        cues = stances["endorses"] + stances["rejects"]
        if example:
            cues.append(_evidence(text, left_start, example, "cue"))
        return ContextReview(
            decision="needs_review",
            reason="The nearby text gives conflicting evidence about author endorsement.",
            evidence=cues,
        )
    if (stances["endorses"] or stances["rejects"]) and not _punctuation_only(reaction):
        return ContextReview(
            decision="needs_review",
            reason="There is a stance cue followed by further commentary. Check the author's full reaction.",
            evidence=stances["endorses"] + stances["rejects"],
        )
    if stances["endorses"]:
        return ContextReview(
            decision="keep",
            reason="The nearby author wording explicitly endorses the passage.",
            evidence=stances["endorses"],
        )
    if stances["rejects"]:
        return ContextReview(
            decision="exclude",
            reason="The nearby author wording explicitly rejects the passage.",
            evidence=stances["rejects"],
        )
    if example and _punctuation_only(reaction):
        return ContextReview(
            decision="exclude",
            reason="The passage is introduced as an illustrative or hypothetical quotation.",
            evidence=[_evidence(text, left_start, example, "cue")],
        )
    # A bare attribution suffices only for an isolated report. Other local
    # wording may express implicit agreement, irony, or criticism.
    if (
        reporting
        and not (pre_self or post_self)
        and right_end == len(text)
        and not text[:left_start].strip()
        and (pre_report or _punctuation_only(left))
        and _punctuation_only(reaction)
    ):
        return ContextReview(
            decision="exclude",
            reason="This standalone passage reports another speaker's words.",
            evidence=reporting,
        )
    if (pre_self or post_self) and not reporting and _punctuation_only(reaction):
        cue = (
            _evidence(text, left_start, pre_self, "cue")
            if pre_self
            else _evidence(text, end, post_self, "cue")
        )
        if text[:left_start].strip():
            return ContextReview(
                decision="needs_review",
                reason="The author quotes their own words. Check whether the surrounding text still endorses them.",
                evidence=[cue],
            )
        return ContextReview(
            decision="keep",
            reason="The author directly attributes these quoted words to themselves.",
            evidence=[cue],
        )
    evidence = reporting or ([_span(text, quote.start(), quote.end())] if quote else [])
    if example:
        evidence.append(_evidence(text, left_start, example, "cue"))
    return ContextReview(
        decision="needs_review",
        reason="The local wording does not settle whether the author adopts this passage.",
        evidence=evidence,
    )


def review_attribution(request: AttributionReviewInput):
    """Return advisory decisions and exact evidence for the supplied highlights."""
    text = request.normalized_text
    quotes = list(_QUOTATIONS.finditer(text))
    quote_ends = [quote.end() for quote in quotes]
    paragraph_breaks = [match.start() for match in re.finditer(r"\n[ \t]*\n", text)]
    grouped = defaultdict(list)
    for annotation in request.annotations:
        grouped[annotation.start, annotation.end].append(annotation.id)

    passages, kept, assessments = [], [], {}
    for (start, end), annotation_ids in sorted(grouped.items()):
        passage = _span(text, start, end)
        index = bisect_right(quote_ends, start)
        quote = quotes[index] if index < len(quotes) and quotes[index].start() < end else None
        # Different rubrics can highlight different spans of the same quote.
        # They share a decision only when each span is contained in that quote.
        key = quote.span() if quote and quote.start() <= start and end <= quote.end() else (start, end)
        if key not in assessments:
            assessments[key] = _review_passage(text, passage, quotes, quote_ends, paragraph_breaks)
        verdict = assessments[key]
        passages.append(PassageReview(annotation_ids=annotation_ids, passage=passage, **verdict.model_dump()))
        if verdict.decision == "keep":
            kept.extend(annotation_ids)
    return AttributionReviewReport(passages=passages, kept_annotation_ids=kept)
