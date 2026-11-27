#!/usr/bin/env python3
"""Extract frames for every video in a folder (or inventory.json)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DEFAULT_INTERVAL, iter_videos, load_json

SCRIPT = Path(__file__).resolve().parent / "extract_frames.py"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Footage folder")
    parser.add_argument("--inventory", type=Path, help="inventory.json from probe.py")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    args = parser.parse_args()

    paths: list[Path] = []
    if args.inventory:
        data = load_json(args.inventory)
        paths = [Path(v["path"]) for v in data.get("videos") or []]
    elif args.input:
        paths = iter_videos(args.input.resolve())
    else:
        raise SystemExit("error: provide --input or --inventory")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        dest = args.out_dir / path.stem
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(path),
            "--out-dir",
            str(dest),
            "--interval",
            str(args.interval),
        ]
        print(f"# {path.name}")
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
