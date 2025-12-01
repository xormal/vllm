#!/usr/bin/env python3
"""
Validate SPEC_TO_CODE_MAPPING.json references actual files/line numbers.

This script is used both locally (via pre-commit) and inside CI to make
sure that new code keeps the mapping in sync with the implementation.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

MAPPING_FILE = Path("SPEC_TO_CODE_MAPPING.json")


def load_mapping() -> dict[str, Any]:
    if not MAPPING_FILE.exists():
        raise FileNotFoundError(f"{MAPPING_FILE} is missing.")
    return json.loads(MAPPING_FILE.read_text())


def parse_line_range(range_value: Any) -> tuple[int, int] | None:
    if isinstance(range_value, (int, float)):
        value = int(range_value)
        return value, value
    if isinstance(range_value, str):
        match = re.match(r"^(\d+)(?:-(\d+))?$", range_value.strip())
        if match:
            start = int(match.group(1))
            end = int(match.group(2) or match.group(1))
            return start, end
    return None


def validate_reference(path: Path, lines: tuple[int, int] | None) -> str | None:
    if not path.exists():
        return f"Referenced file does not exist: {path}"
    if lines is None:
        return None
    total_lines = sum(1 for _ in path.open("r", encoding="utf-8"))
    start, end = lines
    if start < 1 or end > total_lines:
        return (
            f"Line range {start}-{end} is out of bounds for {path} "
            f"(file has {total_lines} lines)"
        )
    return None


def validate_mapping(mapping: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sections = mapping.get("mappings", {})
    for category, entries in sections.items():
        if isinstance(entries, dict):
            iterable = entries.items()
        else:
            iterable = enumerate(entries)
        for key, info in iterable:
            if not isinstance(info, dict):
                continue
            code_file = info.get("code_file")
            if not code_file:
                continue
            path = Path(code_file)
            line_range = parse_line_range(info.get("code_line"))
            error = validate_reference(path, line_range)
            if error:
                errors.append(f"{category}::{key}: {error}")
    return errors


def main() -> None:
    try:
        mapping = load_mapping()
        errors = validate_mapping(mapping)
    except Exception as exc:  # pragma: no cover - guard rail
        print(f"Failed to validate spec mapping: {exc}")
        sys.exit(1)
    if errors:
        print("SPEC_TO_CODE_MAPPING.json validation failed:")
        for error in errors:
            print(f" - {error}")
        sys.exit(1)
    print("SPEC_TO_CODE_MAPPING.json validation passed.")


if __name__ == "__main__":
    main()
