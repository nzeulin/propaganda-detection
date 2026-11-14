"""Stable public job contracts shared through generated OpenAPI types."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class TraceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module: str
    status: Literal["running", "completed", "interrupted"]
    started_at: str
    inputs: dict[str, Any]
    provider: str
    artifact: Any
    elapsed_seconds: float


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: str
    target_id: str
    fingerprint: str
    status: Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
    created_at: str
    updated_at: str
    payload: dict[str, Any]
    trace: list[TraceRecord]
    result: dict[str, Any] | None
    error: dict[str, str] | None
