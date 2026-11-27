"""Render approved overlay props through the package-local Remotion CLI."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from pipeline_common import run_command, write_json_object
from render_rhythm_preview import timeline_duration


FPS = 30


def _relative_asset(source: Path, assets: Path, name: str) -> str:
    destination = assets / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination.relative_to(assets).as_posix()


def build_render_props(edit: dict, base_video: str) -> dict:
    duration = timeline_duration(edit["timeline"])
    width, height = ((1920, 1080) if edit["aspect"] == "16:9" else (1080, 1920))
    props = {"fps": FPS, "width": width, "height": height, "durationInFrames": round(duration * FPS), "baseVideo": base_video, "titles": [], "captions": [], "graphics": []}
    for title in edit["titles"]:
        if title.get("animated"):
            props["titles"].append({"text": title["text"], "startFrame": round(float(title["start_sec"]) * FPS), "durationInFrames": round((float(title["end_sec"]) - float(title["start_sec"])) * FPS), "position": "top", "fontSize": 56, "color": "#ffffff"})
    for caption in edit["captions"]:
        props["captions"].append({"text": caption["text"], "startFrame": round(float(caption["start_sec"]) * FPS), "endFrame": round(float(caption["end_sec"]) * FPS)})
    return props


def render_remotion(base: Path, edit: dict, assets: Path, props_path: Path, output: Path, *, remotion_dir: Path | None = None) -> list[str]:
    """Copy public assets, write props, and invoke Remotion with an explicit license key."""
    license_key = os.environ.get("REMOTION_LICENSE_KEY", "").strip()
    if not license_key:
        raise ValueError("REMOTION_LICENSE_KEY must be explicitly set before rendering")
    base, assets, props_path, output = map(Path, (base, assets, props_path, output))
    assets.mkdir(parents=True, exist_ok=True)
    base_name = _relative_asset(base, assets, "base.mp4")
    props = build_render_props(edit, base_name)
    for index, graphic in enumerate(edit["graphics"]):
        asset = _relative_asset(Path(graphic["file"]), assets, f"graphics/{index}-{Path(graphic['file']).name}")
        props["graphics"].append({"asset": asset, "startFrame": round(float(graphic["start_sec"]) * FPS), "durationInFrames": round((float(graphic["end_sec"]) - float(graphic["start_sec"])) * FPS), "position": graphic["position"], "scale": graphic["scale"], "opacity": graphic["opacity"]})
    write_json_object(props_path, props)
    root = remotion_dir or Path(__file__).resolve().parents[1] / "remotion"
    output.parent.mkdir(parents=True, exist_ok=True)
    log = props_path.parent / "logs" / "remotion.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    command = ["npx", "remotion", "render", "src/index.ts", "AerialPackage", str(output.resolve()), f"--props={props_path.resolve()}", f"--public-dir={assets.resolve()}", "--codec=h264", "--crf=18"]
    with log.open("w", encoding="utf-8") as handle:
        run_command(command, cwd=root, check=True, stdout=handle, stderr=handle)
    return command
