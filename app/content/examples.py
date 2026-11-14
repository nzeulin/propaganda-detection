"""Explicit synthetic fixtures. These providers are never selected for arbitrary input."""

from app.content.schemas import Assessment, Extraction

_MIXED_REBUTTAL = "The people spreading it are vultures who have no place at the table."

ATTRIBUTION_DEMOS = {
    "quote-endorsed": (
        "Quote context · endorsement",
        "The chair wrote, “Only traitors would ask for more time.” I agree with that claim.",
        "The author adopts the chair's claim that asking for more time is disloyal.",
    ),
    "quote-rejected": (
        "Quote context · rebuttal",
        "The chair wrote, “Only traitors would ask for more time.” I reject that claim.",
        "The author rejects the chair's claim that asking for more time is disloyal.",
    ),
    "quote-unclear": (
        "Quote context · ambiguous",
        "The chair wrote, “Only traitors would ask for more time.” Interesting.",
        "The author repeats the chair's claim and gives a brief ambiguous reaction.",
    ),
    "quote-mixed": (
        "Quote context · rebuttal with an attack",
        "The chair called anyone asking for more time a “traitor”. That accusation is baseless.\n\n"
        + _MIXED_REBUTTAL,
        "The author rejects the chair's accusation and then attacks the people spreading it.",
    ),
}

EXAMPLES = {
    "town-hall": {
        "id": "town-hall",
        "title": "A town hall under pressure",
        "label": "Synthetic · worked example",
        "text": (
            "Town hall briefing 🏛️\n\n"
            "If we do not stop this plan, our town will be destroyed. "
            "Only traitors would ask for more time.\n\n"
            "The plan puts everything we love at risk. "
            "If we do not stop this plan, our town will be destroyed.\n\n"
            "A speaker said, “Only traitors would ask for more time.” "
            "The reporter rejected that accusation and called for an open debate."
        ),
        "narrative": "The town must stop the plan immediately; questioning this demand is disloyal.",
    },
    "public-notice": {
        "id": "public-notice",
        "title": "Public meeting notice",
        "label": "Synthetic · informational",
        "text": (
            "The council will discuss its transport plan on Tuesday.\n\n"
            "Residents may submit comments before the meeting. "
            "The proposal and agenda are available at the council office."
        ),
        "narrative": "Residents can participate in the council transport-plan discussion.",
    },
    **{
        key: {
            "id": key,
            "title": title,
            "label": "Synthetic · simulated first-pass highlight",
            "text": text,
            "narrative": narrative,
        }
        for key, (title, text, narrative) in ATTRIBUTION_DEMOS.items()
    },
}


class DemoProvider:
    def __init__(self, example_id: str):
        self.example_id = example_id
        self.models = {"extractor": "offline-fixture-v1", "scorer": "offline-rubric-v1"}

    async def extract(self, text, paragraphs, title, feedback=None):
        example = EXAMPLES[self.example_id]
        if self.example_id in ATTRIBUTION_DEMOS:
            quote_start = text.index("“") + 1
            candidates = [(text[quote_start : text.index("”", quote_start)], "The chair")]
            if self.example_id == "quote-mixed":
                candidates.append((_MIXED_REBUTTAL, None))
            statements = []
            for index, (phrase, speaker_name) in enumerate(candidates, 1):
                start = text.index(phrase, quote_start)
                paragraph = next(p for p in paragraphs if p["start"] <= start < p["end"])
                statements.append(
                    {
                        "id": f"s{index}",
                        "canonical_claim_id": f"s{index}",
                        "text": phrase,
                        "section_id": "sec1",
                        "narrative_id": "n1",
                        "source_spans": [
                            {
                                "start": start,
                                "end": start + len(phrase),
                                "paragraph_id": paragraph["id"],
                                "excerpt": phrase,
                            }
                        ],
                        "context_excerpt": paragraph["text"],
                        "role": "main_conclusion",
                        "speaker": "named_source" if speaker_name else "author",
                        "speaker_name": speaker_name,
                        "stance": "endorsed",
                        "is_direct_quote": speaker_name is not None,
                        "author_attributable": True,
                    }
                )
            return Extraction.model_validate(
                {
                    "narratives": [{"id": "n1", "summary": example["narrative"], "kind": "argumentative"}],
                    "sections": [
                        {
                            "id": "sec1",
                            "title": "Quotation and response",
                            "paragraph_ids": [p["id"] for p in paragraphs],
                        }
                    ],
                    "statements": statements,
                    "patterns": [],
                }
            )
        sections = [
            {"id": "sec1", "title": "Central message", "paragraph_ids": [p["id"] for p in paragraphs[:2]]},
            {
                "id": "sec2",
                "title": "Context and reporting",
                "paragraph_ids": [p["id"] for p in paragraphs[2:]],
            },
        ]
        if self.example_id == "town-hall":
            specs = [
                (
                    "If we do not stop this plan, our town will be destroyed.",
                    "fear",
                    "main_conclusion",
                    "endorsed",
                ),
                ("Only traitors would ask for more time.", "loyalty", "supporting_claim", "endorsed"),
                ("The plan puts everything we love at risk.", "pressure", "supporting_claim", "endorsed"),
                ("Only traitors would ask for more time.", "reported", "counterargument", "rejected"),
            ]
        else:
            specs = [
                (sentence, f"claim{i}", "background", "endorsed")
                for i, sentence in enumerate(
                    [
                        "The council will discuss its transport plan on Tuesday.",
                        "Residents may submit comments before the meeting.",
                        "The proposal and agenda are available at the council office.",
                    ]
                )
            ]
        statements = []
        for phrase, group, role, stance in specs:
            start = 0
            while (start := text.find(phrase, start)) >= 0:
                paragraph = next(p for p in paragraphs if p["start"] <= start < p["end"])
                # The same wording in neutral/rejected reporting remains a separate occurrence/group.
                is_report = paragraph["id"] == "p4" and self.example_id == "town-hall"
                if is_report != (stance == "rejected"):
                    start += len(phrase)
                    continue
                section = next(s for s in sections if paragraph["id"] in s["paragraph_ids"])
                statements.append(
                    {
                        "id": f"s{len(statements) + 1}",
                        "canonical_claim_id": group,
                        "text": phrase,
                        "section_id": section["id"],
                        "narrative_id": "n1",
                        "source_spans": [
                            {
                                "start": start,
                                "end": start + len(phrase),
                                "paragraph_id": paragraph["id"],
                                "excerpt": phrase,
                            }
                        ],
                        "context_excerpt": paragraph["text"],
                        "role": role,
                        "speaker": "named_source" if is_report else "author",
                        "speaker_name": "Town hall speaker" if is_report else None,
                        "stance": stance,
                        "is_direct_quote": is_report,
                        "author_attributable": not is_report,
                    }
                )
                start += len(phrase)
        return Extraction.model_validate(
            {
                "narratives": [
                    {
                        "id": "n1",
                        "summary": example["narrative"],
                        "kind": "argumentative" if self.example_id == "town-hall" else "informational",
                    }
                ],
                "sections": sections,
                "statements": statements,
                "patterns": (
                    [
                        {
                            "feature": "repetition_amplification",
                            "description": "The central threat recurs verbatim.",
                            "statement_ids": [
                                s["id"] for s in statements if s["canonical_claim_id"] == "fear"
                            ],
                        },
                        {
                            "feature": "strategic_persuasion",
                            "description": "Identity pressure discourages scrutiny.",
                            "statement_ids": [
                                s["id"] for s in statements if s["canonical_claim_id"] == "loyalty"
                            ],
                        },
                    ]
                    if self.example_id == "town-hall"
                    else []
                ),
            }
        )

    async def score(self, state, questions):
        target = state.get("target", {})
        result = {}
        for key in questions:
            if key == "relevance":
                level = 1 if target.get("stance") == "rejected" else 4
            elif self.example_id == "public-notice" or key == "authority_manipulation":
                level = 0
            elif key == "repetition_amplification":
                level = 2
            elif key == "strategic_persuasion":
                level = 3
            elif "everything we love" in target.get("text", ""):
                level = 2
            else:
                level = 4 if key == "emotional_manipulation" else 3
            result[key] = Assessment(
                raw_score=level,
                probabilities=[float(i == level) for i in range(5)],
                confidence=1,
                model=self.models["scorer"],
            )
        return result
