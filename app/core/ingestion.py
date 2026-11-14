"""Validate complete imports before creating immutable dataset-scoped observations."""

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1, max_length=200)
    content_id: str = Field(min_length=1, max_length=200)
    action: Literal["created", "reposted", "replied_to", "liked"]
    timestamp: str | None = None
    text: str = Field(default="", max_length=40000)
    url: str | None = Field(default=None, max_length=2048)
    reply_to_content_id: str | None = Field(default=None, max_length=200)
    platform: str = Field(default="unknown", min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_time_and_content(self):
        if not self.account_id.strip() or not self.content_id.strip():
            raise ValueError("Account and content identifiers cannot be whitespace")
        if self.timestamp:
            parsed = datetime.fromisoformat(self.timestamp)
            if parsed.tzinfo is None:
                raise ValueError("Timestamp must include its UTC offset")
            self.timestamp = parsed.astimezone(UTC).isoformat()
        else:
            self.timestamp = None
        if self.action == "created" and not (self.text.strip() or self.url):
            raise ValueError("Created content requires readable text or a URL")
        return self


class DatasetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Untitled investigation", min_length=1, max_length=200)
    text: str | None = Field(default=None, min_length=1, max_length=40000)
    rows: list[dict] | None = Field(default=None, min_length=1, max_length=5000)
    csv: str | None = Field(default=None, min_length=1, max_length=10_000_000)

    @model_validator(mode="after")
    def one_source(self):
        if sum(v is not None for v in (self.text, self.rows, self.csv)) != 1:
            raise ValueError("Supply exactly one of text, rows, or csv")
        return self


def canonical_id(*parts):
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def prepare_dataset(body: DatasetInput):
    raw = body.model_dump(exclude_none=True)
    if len(json.dumps(raw, ensure_ascii=False).encode()) > 10_000_000:
        raise ValueError("Import exceeds 10 MB")
    if body.text is not None:
        rows = [
            {"account_id": "unattributed", "content_id": "material", "action": "created", "text": body.text}
        ]
    elif body.csv is not None:
        reader = csv.DictReader(io.StringIO(body.csv))
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) > 5000:
                raise ValueError("Import exceeds 5,000 events")
    else:
        rows = body.rows
    if not rows:
        raise ValueError("Import contains no observations")
    validated, errors = [], []
    for index, row in enumerate(rows, 1):
        try:
            validated.append(ImportRow.model_validate(row).model_dump())
        except ValidationError as exc:
            errors.append({"row": index, "msg": f"Row {index}: " + "; ".join(e["msg"] for e in exc.errors())})
    if errors:
        raise ValueError(errors)
    dataset_id = canonical_id("dataset", raw)
    nodes, events, contents = {}, {}, {}
    for index, row in enumerate(validated, 1):
        account = canonical_id(dataset_id, "account", row["platform"], row["account_id"])
        content = canonical_id(dataset_id, "content", row["content_id"])
        nodes[account] = {
            "id": account,
            "dataset_id": dataset_id,
            "kind": "account",
            "data": {
                "source_id": row["account_id"],
                "platform": row["platform"],
                "attribution_known": body.text is None,
            },
        }
        if row["action"] == "created":
            record = {
                "source_id": row["content_id"],
                "text": row["text"],
                "url": row["url"],
                "author_id": account if body.text is None else None,
                "created_at": row["timestamp"],
                "reply_to_content_id": row["reply_to_content_id"],
            }
            if content in contents and contents[content] != record:
                raise ValueError(f"Row {index}: conflicting content ID {row['content_id']}")
            contents[content] = record
        event_id = canonical_id(dataset_id, row)
        events[event_id] = {
            "id": event_id,
            "dataset_id": dataset_id,
            "source_id": account,
            "target_id": content,
            "action": row["action"],
            "timestamp": row["timestamp"],
            "data": {"original": rows[index - 1], "normalized": row},
        }
    for observation in events.values():
        if observation["target_id"] not in contents:
            raise ValueError("Interaction references content without a created observation")
    for content_id, record in contents.items():
        parent = record["reply_to_content_id"]
        if parent and canonical_id(dataset_id, "content", parent) not in contents:
            raise ValueError("Reply references unknown content")
        nodes[content_id] = {"id": content_id, "dataset_id": dataset_id, "kind": "content", "data": record}
    return dataset_id, raw, list(nodes.values()), list(events.values())
