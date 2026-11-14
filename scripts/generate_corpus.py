"""Run a small pilot first; rerunning resumes only missing accepted records."""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from app.evaluation.corpus import generate_corpus

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=24, choices=range(1, 1501), metavar="1..1500")
    parser.add_argument("--concurrency", type=int, default=3, choices=range(1, 5))
    parser.add_argument("--output", type=Path, default=Path(".local-data/corpus"))
    args = parser.parse_args()
    load_dotenv()
    print(json.dumps(asyncio.run(generate_corpus(args.output, args.limit, args.concurrency)), indent=2))
