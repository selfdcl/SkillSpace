#!/usr/bin/env python3
"""Cut one library part with ffmpeg. copy ≈ LosslessCut; encode = frame-accurate."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import MAX_PART_SEC, die, has_audio, ffprobe_json, run, which_or_die


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--start", required=True, type=float)
    parser.add_argument("--end", required=True, type=float)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--mode", choices=["copy", "encode"], default="encode")
    args = parser.parse_args()

    if args.end <= args.start:
        die("end must be > start")
    dur = args.end - args.start
    if dur > MAX_PART_SEC + 0.05:
        die(f"part duration {dur:.2f}s exceeds {MAX_PART_SEC}s")

    src = args.src.absolute()
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = which_or_die("ffmpeg")
    meta = ffprobe_json(src)
    audio = has_audio(meta)

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{args.start:.3f}",
        "-to",
        f"{args.end:.3f}",
        "-i",
        str(src),
    ]
    if args.mode == "copy":
        # Keyframe-aligned, fast. May be slightly longer than requested.
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        if not audio:
            cmd += ["-an"]
        else:
            # Drop DJI timed-metadata tracks that break copy on some files.
            cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
    else:
        cmd += [
            "-map",
            "0:v:0",
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
        ]
        if audio:
            cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "128k"]
        else:
            cmd += ["-an"]

    cmd.append(str(out))
    run(cmd)
    print(f"wrote {out} ({dur:.2f}s, mode={args.mode})")


if __name__ == "__main__":
    main()
