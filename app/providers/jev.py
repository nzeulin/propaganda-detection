"""Jev Score adapter; all five descriptive rubric levels come from configuration."""

import asyncio
import os

from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, Score

from app.content.schemas import Assessment


class JevScorer:
    def __init__(self, config, runtime):
        self.config, self.runtime = config, runtime
        self.model = os.getenv("TYPESAFE_MODEL", "jev-latest")
        self.client = AsyncTypeSafeClient(model=self.model, timeout=45, retry=RetryPolicy(max_retries=0))
        self.resolution_lock = asyncio.Lock()
        self.resolved = False

    async def score(self, state, questions):
        payload = {"state": state, "questions": questions}

        async def request():
            response = await self.client.system_one(
                model=self.model,
                state=state,
                questions={
                    key: Score(
                        instructions=f"{self.config.prompts['scoring']} Assess {key} for target (or full material).",
                        criteria=self.config.rubrics[key],
                    )
                    for key in questions
                },
            )
            records = {}
            for key in questions:
                answer = response.scores.get(key)
                if answer is None:
                    continue
                if set(answer.probabilities) != set(range(5)):
                    raise ValueError("Jev returned an incomplete rubric distribution.")
                records[key] = Assessment(
                    raw_score=answer.score,
                    probabilities=[answer.probabilities[i] for i in range(5)],
                    confidence=answer.confidence,
                    model=response.model,
                )
            return records, response.model

        # Resolve an alias once before fan-out, then request the returned model ID for this process.
        if not self.resolved:
            async with self.resolution_lock:
                if not self.resolved:
                    result, self.model = await self.runtime.invoke(
                        self.model, payload, request, provider="Jev"
                    )
                    self.resolved = True
                    return result
        result, self.model = await self.runtime.invoke(self.model, payload, request, provider="Jev")
        return result
