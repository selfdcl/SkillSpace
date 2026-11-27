"""Render an approved aerial edit with FFmpeg, optionally packaging overlays in Remotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pipeline_common import ffmpeg_filter_escape, load_json_object, resolve_look_filter, run_command, sha256_file, write_json_object
from render_proposal import load_looks
from validate_pipeline import validate_bundle


FADE_SECONDS = 0.25


def look_sha256(look_id: str, looks: dict[str, dict]) -> str:
    if look_id in looks:
        return hashlib.sha256(json.dumps(looks[look_id], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return sha256_file(Path(look_id))


def require_approved(approval: dict, edit_hash: str, look_id: str, music_id: str, music_hash: str, look_hash: str) -> None:
    if approval.get("status") != "approved":
        raise ValueError("approval status must be approved")
    if approval.get("edit_sha256") != edit_hash:
        raise ValueError("approval edit_sha256 does not match edit.json")
    if approval.get("look_id") != look_id:
        raise ValueError("approval look_id does not match edit")
    if approval.get("music_id") != music_id:
        raise ValueError("approval music_id does not match edit")
    if approval.get("music_sha256") != music_hash:
        raise ValueError("approval music_sha256 does not match music")
    if approval.get("look_sha256") != look_hash:
        raise ValueError("approval look_sha256 does not match approved look")


def needs_remotion(edit: dict) -> bool:
    return bool(edit.get("captions") or edit.get("graphics") or any(title.get("animated") for title in edit.get("titles", [])))


def geometry(aspect: str) -> tuple[int, int]:
    if aspect == "16:9":
        return 1920, 1080
    if aspect == "9:16":
        return 1080, 1920
    raise ValueError(f"unsupported aspect: {aspect}")


def validate_master_timeline(timeline: list[dict]) -> float:
    if not timeline:
        raise ValueError("timeline must not be empty")
    tail = 0.0
    previous_clip_duration = 0.0
    for index, item in enumerate(timeline):
        clip = float(item["source_out"]) - float(item["source_in"])
        if clip <= 0:
            raise ValueError("timeline item duration must be positive")
        cut_at = float(item["cut_at"])
        transition = item["transition"]
        if index == 0 and abs(cut_at) > 1e-6:
            raise ValueError("timeline must be continuous: first cut_at must be zero")
        if index:
            expected = tail - FADE_SECONDS if transition == "fade" else tail
            if abs(cut_at - expected) > 1e-6:
                if transition == "fade-black":
                    raise ValueError("fade-black cut_at must equal previous tail without overlap")
                raise ValueError("timeline must be continuous")
            if transition == "fade" and (clip < FADE_SECONDS or previous_clip_duration < FADE_SECONDS):
                raise ValueError("fade requires clips at least 0.25 seconds")
            if transition == "fade-black" and (clip < FADE_SECONDS or previous_clip_duration < FADE_SECONDS):
                raise ValueError("fade-black requires both adjacent clips at least 0.25 seconds")
        tail = cut_at + clip
        previous_clip_duration = clip
    return round(tail, 6)


def _drawtext_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")


def _archive_before_replace(path: Path) -> None:
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archived = path.with_name(f"{path.stem}.previous-{stamp}{path.suffix}")
        counter = 2
        while archived.exists():
            archived = path.with_name(f"{path.stem}.previous-{stamp}-{counter}{path.suffix}")
            counter += 1
        shutil.copy2(path, archived)


def _probe_duration(path: Path, ffprobe: str) -> float:
    result = run_command([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def _stabilization_filter(item: dict, part: dict, index: int, work_dir: Path, ffmpeg: str) -> str:
    if not item.get("stabilize", False):
        return ""
    if index < 0:
        raise ValueError("stabilization timeline index must be non-negative")
    stabilization_dir = (Path(work_dir) / "stabilization").resolve()
    stabilization_dir.mkdir(parents=True, exist_ok=True)
    # Timeline-derived names avoid letting an ingest part ID choose a derived path.
    transform = (stabilization_dir / f"clip-{index + 1:04d}.trf").resolve()
    if stabilization_dir not in transform.parents:
        raise ValueError("stabilization transform escapes work directory")
    duration = float(item["source_out"]) - float(item["source_in"])
    run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", part["file"], "-an", "-vf", f"trim=start={float(item['source_in']):.3f}:duration={duration:.3f},setpts=PTS-STARTPTS,vidstabdetect=result='{ffmpeg_filter_escape(transform.resolve())}'", "-f", "null", "NUL"], check=True)
    return f",vidstabtransform=input='{ffmpeg_filter_escape(transform.resolve())}':smoothing=10:optzoom=1"


def build_render_command(library: dict, edit: dict, looks: dict[str, dict], music: Path, output: Path, work_dir: Path, *, ffmpeg: str = "ffmpeg") -> tuple[list[str], float, list[str]]:
    parts = {part["id"]: part for part in library["parts"]}
    duration = validate_master_timeline(edit["timeline"])
    width, height = geometry(edit["aspect"])
    look = resolve_look_filter(edit["look_id"], looks)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    used_ids: list[str] = []
    for item in edit["timeline"]:
        part = parts[item["part_id"]]
        command += ["-i", str(Path(part["file"]))]
        used_ids.append(part["id"])
    command += ["-i", str(music)]
    filters: list[str] = []
    labels: list[str] = []
    for index, item in enumerate(edit["timeline"]):
        part = parts[item["part_id"]]
        clip_duration = float(item["source_out"]) - float(item["source_in"])
        stabilization = _stabilization_filter(item, part, index, work_dir, ffmpeg)
        black_fades = ""
        if item["transition"] == "fade-black":
            black_fades += f",fade=t=in:st=0:d={FADE_SECONDS:.3f}"
        if index + 1 < len(edit["timeline"]) and edit["timeline"][index + 1]["transition"] == "fade-black":
            black_fades += f",fade=t=out:st={clip_duration - FADE_SECONDS:.3f}:d={FADE_SECONDS:.3f}"
        filters.append(f"[{index}:v]trim=start={float(item['source_in']):.3f}:duration={clip_duration:.3f},setpts=PTS-STARTPTS{stabilization},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=30,{look}{black_fades},format=yuv420p[v{index}]")
        labels.append(f"[v{index}]")
    current = "[v0]"
    if len(labels) == 1:
        filters.append("[v0]null[vjoined]")
        current = "[vjoined]"
    else:
        for index, item in enumerate(edit["timeline"][1:], 1):
            out = "[vjoined]" if index == len(labels) - 1 else f"[vx{index}]"
            if item["transition"] == "cut":
                filters.append(f"{current}[v{index}]concat=n=2:v=1:a=0{out}")
            elif item["transition"] == "fade-black":
                filters.append(f"{current}[v{index}]concat=n=2:v=1:a=0{out}")
            else:
                filters.append(f"{current}[v{index}]xfade=transition=fade:duration={FADE_SECONDS:.3f}:offset={float(item['cut_at']):.3f}{out}")
            current = out
    for index, title in enumerate(edit.get("titles", [])):
        if title.get("animated"):
            continue
        out = f"[vt{index}]"
        filters.append(f"{current}drawtext=text='{_drawtext_escape(title['text'])}':fontcolor=white:fontsize=56:x=(w-text_w)/2:y=h*0.08:enable='between(t,{float(title['start_sec']):.3f},{float(title['end_sec']):.3f})'{out}")
        current = out
    music_index = len(edit["timeline"])
    fade_start = max(0.0, duration - 0.15)
    filters.append(f"[{music_index}:a]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,loudnorm=I=-16:LRA=11:TP=-1.5,aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.150,afade=t=out:st={fade_start:.3f}:d=0.150[aout]")
    command += ["-filter_complex", ";".join(filters), "-map", current, "-map", "[aout]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(output)]
    return command, duration, used_ids


def render_ffmpeg(library_path: Path, brief_path: Path, edit_path: Path, approval_path: Path, looks_path: Path, music: Path, work_dir: Path, output_dir: Path, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> Path:
    library, brief, edit, approval = (load_json_object(path) for path in (library_path, brief_path, edit_path, approval_path))
    errors = validate_bundle(library, brief, edit, approval, edit_path=edit_path, check_files=True)
    if errors:
        raise ValueError("; ".join(errors))
    music = Path(music)
    if not music.is_file():
        raise ValueError(f"music file does not exist: {music}")
    looks = load_looks(looks_path)
    planned_duration = validate_master_timeline(edit["timeline"])
    geometry(edit["aspect"])
    resolve_look_filter(edit["look_id"], looks)
    remotion_used = needs_remotion(edit)
    if remotion_used and not os.environ.get("REMOTION_LICENSE_KEY", "").strip():
        raise ValueError("REMOTION_LICENSE_KEY must be explicitly set before rendering")
    if _probe_duration(music, ffprobe) < planned_duration:
        raise ValueError("music duration is shorter than approved timeline")
    edit_hash, music_hash = sha256_file(edit_path), sha256_file(music)
    selected_look_hash = look_sha256(edit["look_id"], looks)
    require_approved(approval, edit_hash, edit["look_id"], edit["music_id"], music_hash, selected_look_hash)
    work_dir, output_dir = Path(work_dir), Path(output_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = work_dir / "base.mp4"
    temporary = work_dir / "base.rendering.mp4"
    command, planned_duration, part_ids = build_render_command(library, edit, looks, music, temporary, work_dir, ffmpeg=ffmpeg)
    run_command(command, check=True)
    _archive_before_replace(base)
    os.replace(temporary, base)
    preview = output_dir / "preview.mp4"
    if remotion_used:
        from render_remotion import render_remotion
        temporary_preview = output_dir / "preview.rendering.mp4"
        render_remotion(base, edit, work_dir / "render-assets", work_dir / "render-props.json", temporary_preview)
        _archive_before_replace(preview)
        os.replace(temporary_preview, preview)
        renderer = "ffmpeg+remotion"
    else:
        _archive_before_replace(preview)
        temporary_preview = output_dir / "preview.rendering.mp4"
        shutil.copy2(base, temporary_preview)
        os.replace(temporary_preview, preview)
        renderer = "ffmpeg"
    report = {"schema": "aerial-edit-report/v1", "edit_sha256": edit_hash, "library_sha256": sha256_file(library_path), "brief_sha256": sha256_file(brief_path), "approval_sha256": sha256_file(approval_path), "music_sha256": music_hash, "look_id": edit["look_id"], "look_sha256": selected_look_hash, "music_id": edit["music_id"], "part_ids": part_ids, "duration": _probe_duration(preview, ffprobe), "preview_sha256": sha256_file(preview), "renderer": renderer}
    if remotion_used:
        report["remotion_version"] = "4.0.515"
    write_json_object(output_dir / "edit-report.json", report)
    return preview


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("library", "brief", "edit", "approval", "looks", "music", "work-dir", "output-dir"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    render_ffmpeg(args.library, args.brief, args.edit, args.approval, args.looks, args.music, args.work_dir, args.output_dir)


if __name__ == "__main__":
    main()
