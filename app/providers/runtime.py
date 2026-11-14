"""Shared bounded transport and version-aware in-memory result cache."""

import asyncio
import copy
import hashlib
import json
import time
from collections import OrderedDict

from fastapi import HTTPException
from openai import APIConnectionError, APIStatusError
from typesafe_sdk import TypeSafeAPIConnectionError, TypeSafeAPIError, TypeSafeError


class ProviderRuntime:
    def __init__(self, versions: dict, capacity=128, ttl=900):
        self.versions, self.capacity, self.ttl = versions, capacity, ttl
        self.cache = OrderedDict()
        self.slots = asyncio.Semaphore(4)

    async def invoke(self, model: str, payload: dict, operation, provider="Provider"):
        encoded = json.dumps([model, self.versions, payload], sort_keys=True, ensure_ascii=False)
        key = hashlib.sha256(encoded.encode()).hexdigest()
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < self.ttl:
            self.cache.move_to_end(key)
            return copy.deepcopy(cached[1])
        for attempt in range(2):
            try:
                async with self.slots:
                    async with asyncio.timeout(50):
                        result, resolved = await operation()
                # The resolved ID is part of the key, including on the initial alias request.
                resolved_key = hashlib.sha256(
                    json.dumps(
                        [resolved, self.versions, payload], sort_keys=True, ensure_ascii=False
                    ).encode()
                ).hexdigest()
                self.cache[resolved_key] = (time.monotonic(), copy.deepcopy((result, resolved)))
                while len(self.cache) > self.capacity:
                    self.cache.popitem(last=False)
                return result, resolved
            except (
                APIConnectionError,
                APIStatusError,
                TypeSafeAPIConnectionError,
                TypeSafeAPIError,
                TimeoutError,
            ) as exc:
                status = getattr(exc, "status_code", getattr(exc, "status", None))
                retryable = status is None or status in (408, 429) or status >= 500
                if not attempt and retryable:
                    await asyncio.sleep(0.5)
                    continue
                if status in (401, 403):
                    raise HTTPException(
                        502,
                        f"{provider} authentication/access rejected (HTTP {status}); check its local API key and model access.",
                    ) from exc
                raise HTTPException(
                    502,
                    f"{provider} request failed or timed out. Check credentials, model access and provider availability.",
                ) from exc
            except TypeSafeError as exc:
                raise HTTPException(
                    502, "Jev returned an unusable response; no substitute scores were used."
                ) from exc
