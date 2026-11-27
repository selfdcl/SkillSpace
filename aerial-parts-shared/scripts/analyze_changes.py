#!/usr/bin/env python3
"""Measure adjacent sampled-frame change with FFmpeg difference frames."""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DEFAULT_INTERVAL, run, which_or_die, write_json

PTS_RE = re.compile(r"pts_time:([0-9.]+)")
YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")


def steady_runs(changes: list[dict], interval: float) -> list[dict]:
    """Suggest boundaries; vision review remains authoritative."""
    if not changes:
        return []
    values = [row["change"] for row in changes if row["change"] > 0]
    median = statistics.median(values) if values else 0.0
    boundaries = [0]
    for i in range(1, len(changes)):
        prev = changes[i - 1]["change"]
        curr = changes[i]["change"]
        ratio = max(prev, curr) / max(min(prev, curr), 0.01)
        crossed_still = median > 0 and (
            (prev < median * 0.35 and curr > median * 0.70)
            or (curr < median * 0.35 and prev > median * 0.70)
        )
        if ratio > 1.6 or crossed_still:
            boundaries.append(i)
    boundaries.append(len(changes))

    runs = []
    for start_i, end_i in zip(boundaries, boundaries[1:]):
        rows = changes[start_i:end_i]
        if not rows:
            continue
        start = max(0.0, rows[0]["to"] - interval)
        end = rows[-1]["to"]
        vals = [row["change"] for row in rows]
        runs.append(
            {
                "from": round(start, 3),
                "to": round(end, 3),
                "duration": round(end - start, 3),
                "mean_change": round(statistics.fmean(vals), 4),
                "variation": round(
                    (statistics.pstdev(vals) / max(statistics.fmean(vals), 0.01)),
                    4,
                ),
                "steady": end - start >= 6.0,
            }
        )
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--width", type=int, default=320)
    args = parser.parse_args()

    src = args.input.absolute()
    if not src.is_file():
        raise SystemExit(f"error: not a file: {src}")
    ffmpeg = which_or_die("ffmpeg")
    vf = (
        f"fps=1/{args.interval},scale={args.width}:-2,"
        "tblend=all_mode=difference,signalstats,metadata=print:file=-"
    )
    proc = run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-f",
            "null",
            "NUL" if sys.platform == "win32" else "/dev/null",
        ]
    )

    changes: list[dict] = []
    current_t: float | None = None
    for line in proc.stdout.splitlines():
        pts = PTS_RE.search(line)
        if pts:
            current_t = float(pts.group(1))
            continue
        yavg = YAVG_RE.search(line)
        if yavg and current_t is not None:
            changes.append(
                {
                    "from": round(max(0.0, current_t - args.interval), 3),
                    "to": round(current_t, 3),
                    "change": round(float(yavg.group(1)), 4),
                }
            )
            current_t = None

    output = {
        "schema": "aerial-frame-change/v1",
        "src": str(src),
        "interval": args.interval,
        "metric": "mean luma of adjacent difference frame; higher means more visual change",
        "warning": "This suggests continuity only. Confirm shot type and quality from JPEGs.",
        "changes": changes,
        "suggested_runs": steady_runs(changes, args.interval),
    }
    write_json(args.output, output)
    print(f"wrote {args.output} ({len(changes)} change intervals)")


if __name__ == "__main__":
    main()
