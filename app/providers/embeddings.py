"""Batched text embeddings with a persistent, content-addressed material cache."""

import asyncio
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

import tiktoken
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.core.database import embedding_cache, utc_now
from app.core.ingestion import canonical_id
from app.providers.usage import record_usage


def unit_vector(values, dimensions):
    """Reject unusable vectors; missing or invalid evidence is never a zero vector."""
    if len(values) != dimensions or any(not math.isfinite(value) for value in values):
        raise ValueError("The embedding provider returned invalid vector dimensions or values.")
    length = math.hypot(*values)
    if not length or not math.isfinite(length):
        raise ValueError("An embedding or averaged vector has zero length.")
    return [value / length for value in values]


class EmbeddingProvider:
    def __init__(self, client, policy):
        self.client, self.policy = client, dict(policy)
        # Two jobs sharing materials must not purchase the same missing vectors concurrently.
        self.lock = asyncio.Lock()

    @classmethod
    def from_env(cls, policy):
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            return None
        return cls(
            AsyncOpenAI(api_key=key, timeout=50, max_retries=0),
            {**policy, "model": os.getenv("AGENT_EMBEDDING_MODEL", "").strip() or policy["model"]},
        )

    def tokenize(self, texts):
        # Keep the tokenizer's downloaded vocabulary inside local application storage.
        os.environ.setdefault(
            "TIKTOKEN_CACHE_DIR", str(Path(__file__).resolve().parents[2] / ".local-data/tokenizers")
        )
        encoding = tiktoken.get_encoding("cl100k_base")
        size = self.policy["chunk_tokens"]
        return [
            (key, tokens[start:start + size])
            for key, text in texts.items()
            for tokens in [encoding.encode(text, disallowed_special=())]
            for start in range(0, len(tokens), size)
        ]

    async def embed_materials(self, database, materials):
        policy = self.policy
        signature = {key: policy[key] for key in ("version", "model", "dimensions", "chunk_tokens")}
        keys = {
            material_id: canonical_id("material-embedding", signature, text)
            for material_id, text in materials.items()
        }
        unique = {keys[material_id]: text for material_id, text in materials.items()}
        async with self.lock:
            cached = set()
            with database.connect() as connection:
                cache_keys = sorted(unique)
                for start in range(0, len(cache_keys), 400):
                    cached.update(connection.execute(
                        select(embedding_cache.c.id).where(embedding_cache.c.id.in_(cache_keys[start:start + 400]))
                    ).scalars())
            missing = {key: text for key, text in unique.items() if key not in cached}
            chunks = await asyncio.to_thread(self.tokenize, missing) if missing else []
            remaining = Counter(key for key, _ in chunks)
            accumulated = defaultdict(list)
            resolved_models = {}
            for start in range(0, len(chunks), policy["batch_size"]):
                batch = chunks[start:start + policy["batch_size"]]
                async with asyncio.timeout(55):
                    response = await self.client.embeddings.create(
                        model=policy["model"], input=[tokens for _, tokens in batch],
                        dimensions=policy["dimensions"], encoding_format="float",
                    )
                record_usage(response.model, response.usage, "agent_embeddings")
                indexed = {item.index: item.embedding for item in response.data}
                if len(response.data) != len(batch) or set(indexed) != set(range(len(batch))):
                    raise ValueError("The embedding provider returned an incomplete or duplicated batch.")
                ready = []
                for index, (key, tokens) in enumerate(batch):
                    vector = unit_vector(indexed[index], policy["dimensions"])
                    if key in resolved_models and resolved_models[key] != response.model:
                        raise ValueError("The embedding provider changed models within one material.")
                    resolved_models[key] = response.model
                    accumulated[key].append((vector, len(tokens)))
                    remaining[key] -= 1
                    if remaining[key]:
                        continue
                    parts = accumulated.pop(key)
                    vector = unit_vector([
                        math.fsum(part[dimension] * weight for part, weight in parts)
                        for dimension in range(policy["dimensions"])
                    ], policy["dimensions"])
                    ready.append({"id": key, "model": response.model, "dimensions": policy["dimensions"],
                                  "vector": vector, "created_at": utc_now()})
                if ready:
                    with database.begin() as connection:
                        connection.execute(insert(embedding_cache).on_conflict_do_nothing(), ready)
        return {
            "material_keys": keys, "model": policy["model"], "dimensions": policy["dimensions"],
            "version": policy["version"],
            "cached_materials": len(cached), "generated_materials": len(unique) - len(cached),
        }
