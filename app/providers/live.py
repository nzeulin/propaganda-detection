"""Compose reusable provider adapters for the text-only content module."""

import hashlib
import json

from app.providers.jev import JevScorer
from app.providers.luna import LunaExtractor
from app.providers.runtime import ProviderRuntime
from app.providers.sol import SolVerifier


class LiveProvider:
    def __init__(self, config):
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    name: getattr(config, name)
                    for name in ("taxonomy", "rubrics", "roles", "policy", "prompts")
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        runtime = ProviderRuntime({**config.versions, "configuration_sha256": fingerprint})
        self.extractor, self.scorer = LunaExtractor(config, runtime), JevScorer(config, runtime)
        self.verifier = SolVerifier(runtime)

    @property
    def models(self):
        return {
            "extractor": self.extractor.model,
            "scorer": self.scorer.model,
            "verifier": self.verifier.model,
        }

    async def extract(self, text, paragraphs, title, feedback=None):
        return await self.extractor.extract(text, paragraphs, title, feedback)

    async def score(self, state, questions):
        return await self.scorer.score(state, questions)

    async def close(self):
        await self.extractor.client.close()
        await self.scorer.client.aclose()
        await self.verifier.client.close()
