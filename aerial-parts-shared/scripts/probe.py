#!/usr/bin/env python3
"""Inventory a footage folder via ffprobe JSON (official ffmpeg tool)."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    VIDEO_EXTS,
    duration_sec,
    ffprobe_json,
    has_audio,
    iter_videos,
    video_stream,
    which_or_die,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan video file(s) into inventory.json")
    parser.add_argument("--input", required=True, type=Path, help="Source video file or footage folder")
    parser.add_argument("--output", required=True, type=Path, help="inventory.json path")
    args = parser.parse_args()

    which_or_die("ffprobe")
    # Path.resolve() calls the Windows realpath API, which fails with WinError
    # 1005 on some otherwise-accessible mapped/NAS volumes.  We only need an
    # absolute source reference, not symlink canonicalization.
    source = args.input.absolute()
    if source.is_file() and source.suffix.lower() in VIDEO_EXTS:
        root = source.parent
        source_videos = [source]
    elif source.is_dir():
        root = source
        source_videos = iter_videos(root)
    else:
        raise SystemExit(f"error: not a video file or directory: {source}")

    videos = []
    errors = []
    for path in source_videos:
        try:
            meta = ffprobe_json(path)
            vs = video_stream(meta)
            videos.append(
                {
                    "path": str(path),
                    "rel": str(path.relative_to(root)).replace("\\", "/"),
                    "duration": round(duration_sec(meta), 3),
                    "width": vs.get("width"),
                    "height": vs.get("height"),
                    "fps": vs.get("avg_frame_rate") or vs.get("r_frame_rate"),
                    "codec": vs.get("codec_name"),
                    "audio": has_audio(meta),
                    "size_bytes": int((meta.get("format") or {}).get("size") or path.stat().st_size),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path), "error": str(exc)})

    write_json(
        args.output,
        {
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_dir": str(root),
            "video_count": len(videos),
            "videos": videos,
            "errors": errors,
        },
    )
    print(f"wrote {args.output} ({len(videos)} videos, {len(errors)} errors)")


if __name__ == "__main__":
    main()
