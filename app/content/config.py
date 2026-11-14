"""Versioned, shared configuration; no provider-specific policy lives in adapters."""

from pathlib import Path

import yaml


class Configuration:
    def __init__(self, root: Path | None = None):
        root = root or Path(__file__).resolve().parents[2] / "config"
        for name in ("taxonomy", "rubrics", "roles", "policy", "prompts"):
            setattr(self, name, yaml.safe_load((root / f"{name}.yaml").read_text()))
        self.features = list(self.taxonomy["features"])
        self.statement_features = self.features[2:5]
        self.versions = {
            name: getattr(self, name)["version"]
            for name in ("taxonomy", "rubrics", "roles", "policy", "prompts")
        }
