"""Build a low-resolution rhythm preview from an approved aerial edit."""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_common import load_json_object, resolve_look_filter, run_command, sha256_file, write_json_object
from render_proposal import part_mapping, timeline_duration, load_looks


FADE_SECONDS = 0.25


def preview_geometry(aspect: str) -> tuple[int, int]:
    if aspect == "16:9":
        return (1280, 720)
    if aspect == "9:16":
        return (720, 1280)
    raise ValueError(f"unsupported aspect: {aspect}")


def validate_timeline(timeline: list[dict]) -> float:
    if not timeline:
        raise ValueError("timeline must not be empty")
    tail = 0.0
    for index, item in enumerate(timeline):
        if item["transition"] not in {"cut", "fade"}:
            raise ValueError("timeline transition must be cut or fade")
        start, end, cut_at = float(item["source_in"]), float(item["source_out"]), float(item["cut_at"])
        if end <= start:
            raise ValueError("timeline item duration must be positive")
        if index == 0:
            if abs(cut_at) > 1e-6:
                raise ValueError("timeline must be continuous: first cut_at must be zero")
        else:
            expected = tail - FADE_SECONDS if item["transition"] == "fade" else tail
            if abs(cut_at - expected) > 1e-6:
                raise ValueError("timeline must be continuous with its transition")
        tail = cut_at + end - start
    return round(tail, 6)


def _music_path(music: Path | None) -> Path:
    if music is None:
        raise ValueError("music file is required")
    music = Path(music)
    if not music.is_file():
        raise ValueError(f"music file does not exist: {music}")
    return music


def build_rhythm_command(library: dict, edit: dict, looks: dict[str, dict], ffmpeg: str, output: Path, music: Path | None) -> list[str]:
    parts = part_mapping(library, edit)
    music = _music_path(music)
    planned_duration = validate_timeline(edit["timeline"])
    width, height = preview_geometry(edit["aspect"])
    look = resolve_look_filter(edit["look_id"], looks)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for item in edit["timeline"]:
        part = parts.get(item["part_id"])
        if part is None:
            raise ValueError(f"unknown part_id: {item['part_id']}")
        command += ["-i", str(Path(part["file"]))]
    command += ["-i", str(music)]
    filters: list[str] = []
    labels: list[str] = []
    for index, item in enumerate(edit["timeline"]):
        clip_duration = float(item["source_out"]) - float(item["source_in"])
        filters.append(f"[{index}:v]trim=start={float(item['source_in']):.3f}:duration={clip_duration:.3f},setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=30,{look},format=yuv420p[v{index}]")
        labels.append(f"[v{index}]")
    if len(labels) == 1:
        filters.append("[v0]null[vout]")
    else:
        current = "[v0]"
        for index, item in enumerate(edit["timeline"][1:], 1):
            out = "[vout]" if index == len(labels) - 1 else f"[xf{index}]"
            if item["transition"] == "fade":
                filters.append(f"{current}[v{index}]xfade=transition=fade:duration={FADE_SECONDS:.3f}:offset={float(item['cut_at']):.3f}{out}")
            else:
                filters.append(f"{current}[v{index}]concat=n=2:v=1:a=0{out}")
            current = out
    maps = ["-map", "[vout]"]
    audio_index = len(edit["timeline"])
    fade_start = max(0, planned_duration - 0.15)
    filters.append(f"[{audio_index}:a]atrim=duration={planned_duration:.3f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.150,afade=t=out:st={fade_start:.3f}:d=0.150[aout]")
    maps += ["-map", "[aout]"]
    command += ["-filter_complex", ";".join(filters), *maps, "-c:v", "libx264", "-crf", "25", "-pix_fmt", "yuv420p"]
    command += ["-c:a", "aac", "-b:a", "160k"]
    return command + [str(Path(output))]


def render_rhythm_preview(library: dict, edit: dict, looks: dict[str, dict], out_dir: Path, music: Path | None, edit_path: Path, *, ffmpeg: str = "ffmpeg") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    music = _music_path(music)
    duration = validate_timeline(edit["timeline"])
    output = out_dir / "rhythm-preview.mp4"
    command = build_rhythm_command(library, edit, looks, ffmpeg, output, music)
    run_command(command, check=True)
    write_json_object(out_dir / "rhythm-preview.json", {"command": command, "output_duration": duration, "part_ids": [item["part_id"] for item in edit["timeline"]], "music_sha256": sha256_file(music), "edit_sha256": sha256_file(edit_path)})
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--edit", required=True, type=Path)
    parser.add_argument("--looks", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--music", required=True, type=Path)
    args = parser.parse_args()
    render_rhythm_preview(load_json_object(args.library), load_json_object(args.edit), load_looks(args.looks), args.out_dir, args.music, args.edit)


if __name__ == "__main__":
    main()
