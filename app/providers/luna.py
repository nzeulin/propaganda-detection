"""OpenAI Responses structured extraction, isolated from domain aggregation."""

import json
import os

from openai import AsyncOpenAI

from app.content.schemas import Extraction


class LunaExtractor:
    def __init__(self, config, runtime):
        self.config, self.runtime = config, runtime
        self.model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
        self.client = AsyncOpenAI(timeout=45, max_retries=0)

    async def extract(self, text, paragraphs, title, feedback=None):
        payload = {"text": text, "paragraphs": paragraphs, "title": title, "validation_feedback": feedback}

        async def request():
            response = await self.client.responses.parse(
                model=self.model,
                instructions=self.config.prompts["extraction"],
                input=json.dumps(payload, ensure_ascii=False),
                text_format=Extraction,
                max_output_tokens=24000,
                store=False,
            )
            if response.output_parsed is None:
                raise ValueError("Extractor refused or returned incomplete structured data.")
            return response.output_parsed, response.model

        result, self.model = await self.runtime.invoke(self.model, payload, request, provider="OpenAI")
        return result
