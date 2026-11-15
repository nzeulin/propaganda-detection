"""Explicit synthetic fixtures. These providers are never selected for arbitrary input."""

from fastapi import HTTPException

from app.content.schemas import Assessment, Extraction

EXAMPLES = {
    "bright-future": {
        "id": "bright-future",
        "title": "Bright Future energy campaign",
        "label": "Synthetic · attribution example",
        "text": (
            "Several local families have reported rising energy bills, adding to concerns about household costs. "
            "The Bright Future campaign has highlighted their experiences and presented a plan that it says "
            "has support from energy specialists. "
            "Anyone who opposes this plan is putting corporate profits ahead of our children’s future. "
            "Organizers say growing public support shows that the town is ready for their approach."
        ),
        "narrative": "Support the campaign's energy plan; opposing it is framed as choosing profits over children.",
    },
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
}


class DemoProvider:
    def __init__(self, example_id: str):
        self.example_id = example_id
        self.models = {"extractor": "offline-fixture-v1", "scorer": "offline-rubric-v1"}

    async def extract(self, text, paragraphs, title, feedback=None):
        example = EXAMPLES[self.example_id]
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
        elif self.example_id == "bright-future":
            specs = [
                ("Several local families have reported rising energy bills, adding to concerns about household costs.",
                 "costs", "background", "endorsed"),
                (("The Bright Future campaign has highlighted their experiences and presented a plan that it says "
                  "has support from energy specialists."), "specialists", "supporting_claim", "neutrally_reported"),
                ("Anyone who opposes this plan is putting corporate profits ahead of our children’s future.",
                 "pressure", "main_conclusion", "endorsed"),
                ("Organizers say growing public support shows that the town is ready for their approach.",
                 "support", "supporting_claim", "neutrally_reported"),
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
                is_report = (
                    paragraph["id"] == "p4" and self.example_id == "town-hall"
                    or self.example_id == "bright-future" and stance == "neutrally_reported"
                )
                if is_report != (stance in ("rejected", "neutrally_reported")):
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
                        "speaker_name": (
                            "Campaign organizers" if self.example_id == "bright-future" else "Town hall speaker"
                        ) if is_report else None,
                        "stance": stance,
                        "is_direct_quote": is_report and self.example_id == "town-hall",
                        "author_attributable": not is_report,
                    }
                )
                start += len(phrase)
        patterns = []
        if self.example_id == "town-hall":
            patterns = [
                {"feature": feature, "description": description,
                 "statement_ids": [s["id"] for s in statements if s["canonical_claim_id"] == group]}
                for feature, description, group in (
                    ("repetition_amplification", "The central threat recurs verbatim.", "fear"),
                    ("strategic_persuasion", "Identity pressure discourages scrutiny.", "loyalty"),
                )
            ]
        elif self.example_id == "bright-future":
            patterns = [{
                "feature": "strategic_persuasion",
                "description": "Opposition is framed as choosing corporate profits over children's futures.",
                "statement_ids": [s["id"] for s in statements if s["canonical_claim_id"] == "pressure"],
            }]
        return Extraction.model_validate(
            {
                "narratives": [
                    {
                        "id": "n1",
                        "summary": example["narrative"],
                        "kind": "informational" if self.example_id == "public-notice" else "argumentative",
                    }
                ],
                "sections": sections,
                "statements": statements,
                "patterns": patterns,
            }
        )

    async def score(self, state, questions):
        target = state.get("target") or {}
        result = {}
        for key in questions:
            if key == "relevance":
                level = 1 if target.get("stance") == "rejected" else 4
            elif self.example_id == "bright-future":
                # Illustrative rubric levels, not predictions from a live model.
                level = 3 if key == "strategic_persuasion" or (
                    "Anyone who opposes" in target.get("text", "")
                    and key in ("emotional_manipulation", "logical_manipulation")
                ) else 0
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

    async def score_batch(self, context, jobs):
        assessments, errors = {}, {}
        for key, target, questions in jobs:
            try:
                assessments[key] = await self.score({**context, "target": target}, questions)
            except (HTTPException, ValueError, TimeoutError) as exc:
                assessments[key] = {}
                errors[key] = str(getattr(exc, "detail", exc))
        return assessments, errors
