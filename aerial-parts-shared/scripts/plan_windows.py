#!/usr/bin/env python3
"""Plan <=6s windows across visually changing runs from changes.json."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_json, write_json


def windows(start: float, end: float, size: float, max_gap: float) -> list[dict]:
    duration = end - start
    if duration <= size:
        return [{"in": round(start, 3), "out": round(end, 3)}]
    count = math.ceil((duration - size) / (size + max_gap)) + 1
    step = (duration - size) / (count - 1)
    return [
        {
            "in": round(start + i * step, 3),
            "out": round(start + i * step + size, 3),
        }
        for i in range(count)
    ]


def assign_phases(items: list[dict]) -> None:
    count = len(items)
    for i, item in enumerate(items):
        if i == 0:
            item["phase"] = "起势"
        elif i == count - 1:
            item["phase"] = "收束"
        elif i >= max(1, count - 2):
            item["phase"] = "高潮"
        else:
            item["phase"] = "发展"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--changes", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--window", type=float, default=5.0)
    parser.add_argument("--max-gap", type=float, default=2.0)
    parser.add_argument("--min-run", type=float, default=6.0)
    args = parser.parse_args()
    if not 0 < args.window <= 6:
        raise SystemExit("error: --window must be >0 and <=6")
    if not 0 <= args.max_gap <= 2:
        raise SystemExit("error: --max-gap must be between 0 and 2")

    data = load_json(args.changes)
    groups = []
    for index, run in enumerate(data.get("suggested_runs") or [], start=1):
        if not run.get("steady") or float(run["duration"]) < args.min_run:
            continue
        items = windows(
            float(run["from"]),
            float(run["to"]),
            args.window,
            args.max_gap,
        )
        assign_phases(items)
        group_id = f"motion_{index:02d}"
        for item in items:
            item["motion_group"] = group_id
        groups.append(
            {
                "motion_group": group_id,
                "from": run["from"],
                "to": run["to"],
                "mean_change": run["mean_change"],
                "variation": run["variation"],
                "windows": items,
            }
        )

    write_json(
        args.output,
        {
            "schema": "aerial-window-plan/v1",
            "src": data.get("src"),
            "window": args.window,
            "max_gap": args.max_gap,
            "warning": "Candidates only. Read corresponding JPEGs before tagging/cutting.",
            "groups": groups,
        },
    )
    total = sum(len(group["windows"]) for group in groups)
    print(f"wrote {args.output} ({len(groups)} groups, {total} windows)")


if __name__ == "__main__":
    main()
