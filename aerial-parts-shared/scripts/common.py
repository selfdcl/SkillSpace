#!/usr/bin/env python3
"""ffmpeg/ffprobe helpers. Stdlib only. Windows-safe (no shell=True)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".insv", ".avi"}
MAX_PART_SEC = 6.0
DEFAULT_INTERVAL = 2.0
DEFAULT_FRAME_WIDTH = 1280


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def which_or_die(name: str) -> str:
    path = shutil.which(name)
    if not path:
        die(
            f"未找到 {name}。Windows 可执行: winget install Gyan.FFmpeg "
            "然后重开终端。"
        )
    return path


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ffprobe_json(path: Path) -> dict:
    ffprobe = which_or_die("ffprobe")
    proc = run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return json.loads(proc.stdout)


def duration_sec(meta: dict) -> float:
    fmt = meta.get("format") or {}
    if fmt.get("duration"):
        return float(fmt["duration"])
    for stream in meta.get("streams") or []:
        if stream.get("codec_type") == "video" and stream.get("duration"):
            return float(stream["duration"])
    die(f"无法读取时长: {meta.get('format', {}).get('filename')}")
    return 0.0


def has_audio(meta: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in meta.get("streams") or [])


def video_stream(meta: dict) -> dict:
    for stream in meta.get("streams") or []:
        if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get(
            "attached_pic"
        ):
            return stream
    die("未找到视频流")
    return {}


def iter_videos(root: Path) -> list[Path]:
    files = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    ]
    return files


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
