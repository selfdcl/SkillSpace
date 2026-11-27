#!/usr/bin/env python3
"""Create unreviewed candidate parts from an objective window plan."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import MAX_PART_SEC, load_json, write_json


def default_id_prefix(src: str) -> str:
    stem = Path(src).stem
    suffix = stem[4:] if stem.upper().startswith("DJI_") else stem
    return f"sel_{suffix.lower()}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build automatic candidates without extracting or viewing frames"
    )
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--window-plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--id-prefix")
    args = parser.parse_args()

    inventory = load_json(args.inventory)
    plan = load_json(args.window_plan)
    src = str(plan.get("src") or "")
    videos = inventory.get("videos") or []
    video = next((item for item in videos if str(item.get("path")) == src), None)
    if not src or video is None:
        raise SystemExit("error: window-plan src must match one inventory video")

    prefix = args.id_prefix or default_id_prefix(src)
    candidates = []
    for group in plan.get("groups") or []:
        group_id = group.get("motion_group")
        for window in group.get("windows") or []:
            start = float(window["in"])
            end = float(window["out"])
            duration = end - start
            if duration <= 0 or duration > MAX_PART_SEC + 0.001:
                raise SystemExit(
                    f"error: invalid window {start:.3f}-{end:.3f}; duration must be >0 and <=6"
                )
            if start < 0 or end > float(video["duration"]) + 0.001:
                raise SystemExit(f"error: window outside source duration: {start:.3f}-{end:.3f}")
            candidates.append(
                {
                    "id": f"{prefix}_{len(candidates) + 1:03d}",
                    "src": src,
                    "in": round(start, 3),
                    "out": round(end, 3),
                    "dur": round(duration, 3),
                    "shot": "未定",
                    "subject": "未定",
                    "light": "未定",
                    "move": "连续运镜",
                    "motion_group": window.get("motion_group") or group_id,
                    "phase": window.get("phase"),
                    "quality": "可用",
                    "note": "自动窗口，未人工判片",
                }
            )

    width = video.get("width")
    height = video.get("height")
    write_json(
        args.output,
        {
            "src": src,
            "duration": video.get("duration"),
            "resolution": f"{width}x{height}" if width and height else "",
            "fps": video.get("fps"),
            "audio": bool(video.get("audio")),
            "light": "未定",
            "selection_mode": "automatic",
            "window_plan": str(args.window_plan.absolute()),
            "review_note": "依据变化曲线自动生成，未做人工判片；按自动窗口规则标为可用。",
            "keep": candidates,
        },
    )
    print(f"wrote {args.output} ({len(candidates)} automatic candidates)")


if __name__ == "__main__":
    main()
