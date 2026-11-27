#!/usr/bin/env python3
"""Render edit.json against library.json with ffmpeg xfade or hard cuts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import die, duration_sec, ffprobe_json, load_json, run, which_or_die


def part_map(library: dict) -> dict[str, dict]:
    return {p["id"]: p for p in library.get("parts") or []}


def build_filter(n: int, durations: list[float], fade: float, width: int, height: int, fps: int) -> str:
    parts: list[str] = []
    for i in range(n):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,"
            f"setpts=PTS-STARTPTS[v{i}]"
        )
    if n == 1:
        parts.append("[v0]copy[vout]")
        return ";".join(parts)
    if fade <= 0:
        concat_in = "".join(f"[v{i}]" for i in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")
        return ";".join(parts)

    offset = durations[0] - fade
    last = "[v0]"
    for i in range(1, n):
        out = "[vout]" if i == n - 1 else f"[vx{i}]"
        src = last if i == 1 else f"[vx{i-1}]"
        parts.append(
            f"{src}[v{i}]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}{out}"
        )
        offset += durations[i] - fade
        last = out
    return ";".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--edit", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--transition", choices=["none", "fade"], default="fade")
    parser.add_argument("--xfade", type=float, default=0.4)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    library = load_json(args.library)
    edit = load_json(args.edit)
    ids = edit.get("part_ids")
    if not isinstance(ids, list) or not ids:
        die("edit.json must contain non-empty part_ids")

    mapping = part_map(library)
    files: list[Path] = []
    durations: list[float] = []
    for pid in ids:
        part = mapping.get(pid)
        if not part:
            die(f"unknown part id: {pid}")
        path = Path(part["file"])
        if not path.is_file():
            die(f"part file missing: {path}")
        files.append(path)
        durations.append(float(part["dur"]))

    ffmpeg = which_or_die("ffmpeg")
    fade = 0.0 if args.transition == "none" else args.xfade
    if fade > 0:
        for d in durations:
            if d <= fade + 0.05:
                die(f"part shorter than xfade ({d}s <= {fade}s); use --transition none")

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    filt = build_filter(len(files), durations, fade, args.width, args.height, args.fps)

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for path in files:
        cmd += ["-i", str(path)]
    cmd += [
        "-filter_complex",
        filt,
        "-map",
        "[vout]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    run(cmd)
    try:
        got = duration_sec(ffprobe_json(out))
    except Exception:
        got = -1
    print(f"wrote {out} ({got:.2f}s, clips={len(files)}, transition={args.transition})")


if __name__ == "__main__":
    main()
