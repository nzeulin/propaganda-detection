"""Export the application schema without loading credentials or starting providers."""

import json
from pathlib import Path

from app.main import app

output = Path(__file__).resolve().parents[1] / ".copilot-cache/openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), indent=2))
