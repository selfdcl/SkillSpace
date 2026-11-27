#!/usr/bin/env python3
"""Cut approved candidates; marginal candidates require explicit opt-in."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import die, load_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-cut candidates. By default only quality=可用 is cut."
    )
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=["copy", "encode"], default="encode")
    parser.add_argument(
        "--include-marginal",
        action="store_true",
        help="also cut candidates whose quality is 勉强",
    )
    args = parser.parse_args()

    data = load_json(args.candidates)
    candidates = data.get("keep")
    if not isinstance(candidates, list):
        die("candidates JSON must contain a keep list")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    cut_script = Path(__file__).resolve().parent / "cut_part.py"
    cut_count = 0
    skipped_marginal = 0
    skipped_rejected = 0

    for item in candidates:
        quality = item.get("quality")
        if quality == "勉强" and not args.include_marginal:
            skipped_marginal += 1
            continue
        if quality == "废片":
            skipped_rejected += 1
            continue
        if quality not in {"可用", "勉强"}:
            die(f"candidate {item.get('id', '<missing id>')} has invalid quality: {quality}")

        missing = [key for key in ("id", "src", "in", "out") if key not in item]
        if missing:
            die(f"candidate is missing fields {missing}: {item}")
        output = args.out_dir / f"{item['id']}.mp4"
        subprocess.run(
            [
                sys.executable,
                str(cut_script),
                "--src",
                str(item["src"]),
                "--start",
                str(item["in"]),
                "--end",
                str(item["out"]),
                "--out",
                str(output),
                "--mode",
                args.mode,
            ],
            check=True,
        )
        cut_count += 1

    print(
        f"cut {cut_count}; skipped {skipped_marginal} marginal; "
        f"skipped {skipped_rejected} rejected"
    )


if __name__ == "__main__":
    main()
