"""Small, dependency-free helpers shared by the aerial pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Sequence


def load_json_object(path: Path) -> dict:
    """Load a UTF-8 JSON object, rejecting non-object documents."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def write_json_object(path: Path, value: dict) -> None:
    """Atomically write a UTF-8 JSON object through a sibling .tmp file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest without loading the entire file into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ffmpeg_filter_escape(value: Path | str) -> str:
    """Escape a local path embedded in an FFmpeg filter expression."""
    return str(value).replace("\\", "/").replace(":", "\\:").replace(" ", "\\ ").replace("'", "\\'").replace(",", "\\,")


def resolve_look_filter(look_id: str, looks: dict[str, dict]) -> str:
    """Return a built-in filter or a readable local .cube filter, fail closed otherwise."""
    if look_id in looks:
        value = looks[look_id].get("vf")
        if isinstance(value, str) and value:
            return value
        raise ValueError(f"built-in look has no usable vf: {look_id}")
    lut = Path(look_id)
    if lut.suffix.lower() != ".cube" or not lut.is_file():
        raise ValueError(f"unknown look_id or unreadable approved .cube: {look_id}")
    try:
        with lut.open("rb") as handle:
            handle.read(1)
    except OSError as exc:
        raise ValueError(f"unknown look_id or unreadable approved .cube: {look_id}") from exc
    return f"lut3d=file='{ffmpeg_filter_escape(lut.resolve())}'"


def run_command(args: Sequence[str | Path], **kwargs: Any) -> subprocess.CompletedProcess:
    """Run an argument array with shell expansion disabled."""
    return subprocess.run([str(item) for item in args], shell=False, **kwargs)
