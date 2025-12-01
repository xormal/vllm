#!/usr/bin/env python3
"""
Monitor DOC_responses.md and DOC_streaming_events.md for modifications.

Stores SHA256 hashes in .spec_history.json and writes a summary of changes
to .spec_change_summary.json so CI can raise alerts automatically.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

SPEC_FILES = [
    Path("DOC_responses.md"),
    Path("DOC_streaming_events.md"),
]
HISTORY_FILE = Path(".spec_history.json")
SUMMARY_FILE = Path(".spec_change_summary.json")


def compute_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_history() -> dict[str, Any]:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {"files": {}}


def save_history(history: dict[str, Any]) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def monitor_specs() -> list[dict[str, str]]:
    history = load_history()
    files_history = history.setdefault("files", {})
    changes: list[dict[str, str]] = []

    for spec_path in SPEC_FILES:
        if not spec_path.exists():
            continue
        digest = compute_hash(spec_path)
        record = files_history.get(spec_path.name)
        if record is None:
            files_history[spec_path.name] = {
                "hash": digest,
                "last_updated": datetime.utcnow().isoformat(),
            }
            changes.append(
                {
                    "file": spec_path.name,
                    "status": "baseline_created",
                    "hash": digest[:12],
                }
            )
        elif record.get("hash") != digest:
            changes.append(
                {
                    "file": spec_path.name,
                    "status": "modified",
                    "previous_hash": record.get("hash", "")[:12],
                    "new_hash": digest[:12],
                }
            )
            record["hash"] = digest
            record["last_updated"] = datetime.utcnow().isoformat()
    if changes:
        save_history(history)
    return changes


def main() -> None:
    changes = monitor_specs()
    if changes:
        print("Specification changes detected:")
        for change in changes:
            status = change["status"]
            file = change["file"]
            if status == "modified":
                print(
                    f" - {file}: {change['previous_hash']} -> {change['new_hash']}"
                )
            else:
                print(f" - {file}: baseline recorded ({change['hash']})")
        summary_payload = [
            change for change in changes if change["status"] == "modified"
        ]
        if summary_payload:
            SUMMARY_FILE.write_text(json.dumps(summary_payload, indent=2))
    else:
        print("No specification changes detected.")
        if SUMMARY_FILE.exists():
            SUMMARY_FILE.unlink()


if __name__ == "__main__":
    main()
