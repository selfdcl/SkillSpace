#!/usr/bin/env python3
"""Extract timestamped JPEGs for vision review (video-frames-skill pattern)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DEFAULT_FRAME_WIDTH,
    DEFAULT_INTERVAL,
    duration_sec,
    ffprobe_json,
    run,
    which_or_die,
    write_json,
)


def timestamps(duration: float, interval: float) -> list[float]:
    if duration <= 0:
        return [0.0]
    times: list[float] = []
    t = 0.0
    while t < duration - 0.05:
        times.append(round(t, 3))
        t += interval
    last = round(max(duration - 0.12, 0.0), 3)
    if not times or last - times[-1] >= interval * 0.4:
        times.append(last)
    return times


def extract_one(src: Path, t: float, out: Path, width: int) -> None:
    ffmpeg = which_or_die("ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:-2"
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-vf",
            vf,
            "-q:v",
            "3",
            "-y",
            str(out),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="One video file")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--width", type=int, default=DEFAULT_FRAME_WIDTH)
    args = parser.parse_args()

    src = args.input.absolute()
    if not src.is_file():
        raise SystemExit(f"error: not a file: {src}")

    which_or_die("ffmpeg")
    dur = duration_sec(ffprobe_json(src))
    times = timestamps(dur, args.interval)
    stem = src.stem
    frames = []
    for i, t in enumerate(times):
        name = f"{stem}_t{t:07.1f}s.jpg".replace(" ", "_")
        dest = args.out_dir / name
        extract_one(src, t, dest, args.width)
        frames.append({"file": str(dest), "t": t, "index": i})

    index_path = args.out_dir / f"{stem}_frames.json"
    write_json(
        index_path,
        {
            "src": str(src),
            "duration": dur,
            "interval": args.interval,
            "frames": frames,
        },
    )
    print(f"extracted {len(frames)} frames -> {args.out_dir} (index {index_path})")


if __name__ == "__main__":
    main()
