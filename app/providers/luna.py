"""OpenAI Responses structured extraction, isolated from domain aggregation."""

import json
import os

from openai import AsyncOpenAI

from app.content.schemas import Extraction, SourceExcerpt, StatementContent
from app.content.validation import anchor_extraction
from app.providers.usage import record_usage


class QuotedStatement(StatementContent):
    source_spans: list[SourceExcerpt]


class QuotedExtraction(Extraction):
    """Provider output omits coordinates and context that the application can derive exactly."""

    statements: list[QuotedStatement]


class LunaExtractor:
    def __init__(self, config, runtime):
        self.config, self.runtime = config, runtime
        self.model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
        self.client = AsyncOpenAI(timeout=45, max_retries=0)

    async def extract(self, text, paragraphs, title, feedback=None):
        payload = {
            "text": text,
            "paragraphs": paragraphs,
            "title": title,
            "assessment_unit": (
                "paragraph_or_sentence_pair"
                if len(text) >= self.config.prompts["passage_threshold_characters"]
                else "statement"
            ),
            "validation_feedback": feedback,
        }

        async def request():
            response = await self.client.responses.parse(
                model=self.model,
                instructions=self.config.prompts["extraction"],
                input=json.dumps(payload, ensure_ascii=False),
                text_format=QuotedExtraction,
                max_output_tokens=24000,
                store=False,
            )
            record_usage(response.model, getattr(response, "usage", None), "extraction")
            if response.output_parsed is None:
                raise ValueError("Extractor refused or returned incomplete structured data.")
            extraction = anchor_extraction(response.output_parsed.model_dump(), text, paragraphs)
            return extraction, response.model

        result, self.model = await self.runtime.invoke(self.model, payload, request, provider="OpenAI")
        return result
