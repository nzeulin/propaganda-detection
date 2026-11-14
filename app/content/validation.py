"""Validate frozen source coordinates, then group equivalent claims without losing occurrences."""

from collections import defaultdict

from app.content.schemas import Extraction


def validate_and_group(extraction: Extraction, text: str, paragraphs: list[dict]):
    warnings, valid = [], []
    paragraph_map = {p["id"]: p for p in paragraphs}
    narrative_ids = {n.id for n in extraction.narratives}
    section_map = {s.id: s for s in extraction.sections}
    if len(section_map) != len(extraction.sections) or len(narrative_ids) != len(extraction.narratives):
        return [], ["Duplicate section or narrative identifiers; extraction is invalid."]
    seen = set()
    for statement in extraction.statements:
        issues = []
        if statement.id in seen:
            issues.append("duplicate statement identifier")
        seen.add(statement.id)
        section = section_map.get(statement.section_id)
        if section is None or statement.narrative_id not in narrative_ids:
            issues.append("unknown section/narrative")
        if not statement.source_spans:
            issues.append("missing source spans")
        for span in statement.source_spans:
            paragraph = paragraph_map.get(span.paragraph_id)
            if (
                span.start >= span.end
                or span.end > len(text)
                or not span.excerpt.strip()
                or text[span.start : span.end] != span.excerpt
                or paragraph is None
                or not paragraph["start"] <= span.start < span.end <= paragraph["end"]
                or (section and span.paragraph_id not in section.paragraph_ids)
            ):
                issues.append("source span/excerpt does not match frozen text, paragraph or section")
        if statement.author_attributable and statement.stance != "endorsed":
            issues.append("attribution conflicts with author stance")
        if issues:
            warnings.append(f"Omitted {statement.id}: {'; '.join(sorted(set(issues)))}.")
        else:
            valid.append(statement)
    groups = defaultdict(list)
    exact_groups = {}
    for statement in sorted(valid, key=lambda s: min(span.start for span in s.source_spans)):
        attribution = (
            statement.speaker,
            statement.speaker_name,
            statement.stance,
            statement.author_attributable,
            statement.narrative_id,
        )
        # Also collapse exact proposition duplicates if extraction gave them different group IDs.
        exact_key = (" ".join(statement.text.casefold().split()), attribution)
        group_key = exact_groups.setdefault(exact_key, (statement.canonical_claim_id, attribution))
        groups[group_key].append(statement)
    canonical = []
    for index, occurrences in enumerate(groups.values()):
        first = occurrences[0]
        item = first.model_dump()
        item.update(
            id=f"c{index + 1}",
            canonical_claim_id=f"c{index + 1}",
            occurrences=[o.model_dump() for o in occurrences],
            occurrence_count=len(occurrences),
            relevance=None,
            role_coefficient=None,
            weight=None,
            features={},
            assessments={},
            contributions={},
            assessment_status={},
        )
        canonical.append(item)
    return canonical, warnings
