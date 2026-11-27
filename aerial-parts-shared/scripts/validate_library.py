#!/usr/bin/env python3
"""Validate aerial-parts/v1 library.json without extra pip packages."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import MAX_PART_SEC, load_json

SHOTS = {"拉升", "环绕", "横移", "俯冲", "悬停", "未定"}
LIGHTS = {"日出", "日落", "晴", "阴", "夜景", "黄金时刻", "未定"}
QUALITIES = {"可用", "勉强"}


def validate(data: dict, *, check_files: bool) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "aerial-parts/v1":
        errors.append("schema must be aerial-parts/v1")
    for key in ("created", "source_dir", "parts_dir", "parts"):
        if key not in data:
            errors.append(f"missing {key}")
    parts = data.get("parts")
    if not isinstance(parts, list):
        errors.append("parts must be an array")
        return errors

    ids: set[str] = set()
    for i, part in enumerate(parts):
        prefix = f"parts[{i}]"
        if not isinstance(part, dict):
            errors.append(f"{prefix} not an object")
            continue
        for key in (
            "id",
            "src",
            "in",
            "out",
            "file",
            "dur",
            "shot",
            "subject",
            "light",
            "move",
            "quality",
            "note",
        ):
            if key not in part:
                errors.append(f"{prefix} missing {key}")
        pid = part.get("id")
        if pid in ids:
            errors.append(f"duplicate id {pid}")
        ids.add(pid)
        try:
            start = float(part["in"])
            end = float(part["out"])
            dur = float(part["dur"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            errors.append(f"{prefix} out must be > in")
        if abs((end - start) - dur) > 0.08:
            errors.append(f"{prefix} dur mismatch with out-in")
        if dur > MAX_PART_SEC + 0.05:
            errors.append(f"{prefix} dur {dur} > {MAX_PART_SEC}")
        if part.get("shot") not in SHOTS:
            errors.append(f"{prefix} invalid shot")
        if part.get("light") not in LIGHTS:
            errors.append(f"{prefix} invalid light")
        if part.get("quality") not in QUALITIES:
            errors.append(f"{prefix} invalid quality (废片 must not be stored)")
        if check_files:
            if not Path(part.get("file", "")).is_file():
                errors.append(f"{prefix} missing file {part.get('file')}")
            if not Path(part.get("src", "")).is_file():
                errors.append(f"{prefix} missing src {part.get('src')}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("library", type=Path)
    parser.add_argument("--check-files", action="store_true")
    args = parser.parse_args()
    data = load_json(args.library)
    errors = validate(data, check_files=args.check_files)
    if errors:
        print("INVALID")
        for err in errors:
            print(f"- {err}")
        raise SystemExit(1)
    print(f"OK ({len(data.get('parts', []))} parts)")


if __name__ == "__main__":
    main()
