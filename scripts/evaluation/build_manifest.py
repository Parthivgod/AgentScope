"""Build a SHA-256 index for an evaluation artifact directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from common import artifact_index, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **artifact_index(args.directory),
    }
    write_json(args.directory / "manifest.json", payload)
    print(f"indexed {len(payload['files'])} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
