"""Render storyboard, look contact sheets, and a beat map for an aerial edit."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline_common import load_json_object, resolve_look_filter, run_command
from validate_pipeline import validate_bundle


def representative_time(source_in: float, source_out: float) -> float:
    return round((float(source_in) + float(source_out)) / 2, 6)


def load_looks(path: Path) -> dict[str, dict]:
    value = load_json_object(path)
    if value.get("schema") != "aerial-looks/v1" or not isinstance(value.get("looks"), list):
        raise ValueError("looks must use aerial-looks/v1")
    result = {look["id"]: look for look in value["looks"] if isinstance(look, dict) and isinstance(look.get("id"), str) and isinstance(look.get("vf"), str)}
    if list(result) != ["natural", "warm-gold", "teal-orange"]:
        raise ValueError("looks must contain natural, warm-gold, teal-orange")
    return result


def timeline_duration(timeline: list[dict]) -> float:
    return round(max((float(item["cut_at"]) + float(item["source_out"]) - float(item["source_in"]) for item in timeline), default=0.0), 6)


def validate_music_analysis(analysis: dict, music_id: str) -> None:
    if not isinstance(analysis, dict) or analysis.get("schema") != "aerial-music-analysis/v1":
        raise ValueError("music analysis schema must be aerial-music-analysis/v1")
    if analysis.get("music_id") != music_id:
        raise ValueError("music analysis music_id does not match edit")
    duration = analysis.get("duration")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("music analysis duration must be finite and positive")
    for name in ("beats", "accents"):
        values = analysis.get(name)
        if not isinstance(values, list):
            raise ValueError(f"music analysis {name} must be an array")
        previous = -1.0
        for value in values:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= duration or value < previous:
                raise ValueError(f"music analysis {name} must be finite, ordered, and in range")
            previous = float(value)
    sections = analysis.get("sections")
    if not isinstance(sections, list):
        raise ValueError("music analysis sections must be an array")
    previous = 0.0
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("music analysis section must be an object")
        start, end = section.get("in"), section.get("out")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in (start, end)) or start < previous or end < start or end > duration:
            raise ValueError("music analysis sections must be finite, ordered, and in range")
        previous = float(end)


def _brief(edit: dict) -> dict:
    return {"schema": "aerial-brief/v1", "theme": "proposal", "target_sec": edit.get("target_sec"),
            "platform": "preview", "aspect": "16:9", "pace": "normal", "look_request": "preview",
            "titles": False, "subtitles": False, "voiceover": False,
            "music": {"source": "local", "vocal": False, "commercial_required": False}}


def part_mapping(library: dict, edit: dict) -> dict[str, dict]:
    errors = validate_bundle(library, _brief(edit), edit)
    if errors:
        raise ValueError("; ".join(errors))
    return {part["id"]: part for part in library["parts"]}


def _font() -> ImageFont.ImageFont:
    return ImageFont.load_default()


def _sheet(cells: list[tuple[Image.Image, list[str]]], output: Path, title: str) -> None:
    width, height, text_height = 360, 280, 92
    image = Image.new("RGB", (width * 2, 36 + ((len(cells) + 1) // 2) * height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((12, 10), title, fill="black", font=_font())
    for index, (frame, lines) in enumerate(cells):
        x, y = (index % 2) * width, 36 + (index // 2) * height
        frame.thumbnail((width - 12, height - text_height - 12))
        image.paste(frame, (x + 6, y + 6))
        draw.multiline_text((x + 6, y + height - text_height), "\n".join(lines), fill="black", font=_font(), spacing=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=90)


def render_proposal(library: dict, edit: dict, looks: dict[str, dict], out_dir: Path, *, music_analysis: dict | None = None, ffmpeg: str = "ffmpeg") -> None:
    parts = part_mapping(library, edit)
    out_dir = Path(out_dir)
    work = out_dir / ".frames"
    work.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[Image.Image, list[str]]] = []
    for sequence, item in enumerate(edit["timeline"], 1):
        part = parts[item["part_id"]]
        part_file = Path(part["file"])
        if not part_file.is_file():
            raise ValueError(f"part file does not exist: {part_file}")
        # PNG avoids platform JPEG encoders rejecting limited-range YUV frames.
        frame_path = work / f"{sequence}.png"
        run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{representative_time(item['source_in'], item['source_out']):.3f}", "-i", str(part_file), "-frames:v", "1", str(frame_path)], check=True)
        with Image.open(frame_path) as opened:
            frame = opened.convert("RGB").copy()
        duration = float(item["source_out"]) - float(item["source_in"])
        frames.append((frame, [f"#{sequence} {item['part_id']}  {item['role']}  {duration:.2f}s", f"{part['shot']} | {part['subject']} | {part['light']}"]))
    _sheet(frames, out_dir / "storyboard.jpg", "Storyboard")
    for look_id, look in looks.items():
        cells: list[tuple[Image.Image, list[str]]] = []
        for sequence, (_, labels) in enumerate(frames, 1):
            filtered = work / f"{look_id}-{sequence}.png"
            source = work / f"{sequence}.png"
            run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vf", look["vf"], "-frames:v", "1", str(filtered)], check=True)
            with Image.open(filtered) as opened:
                cells.append((opened.convert("RGB").copy(), [look["label"], *labels]))
        _sheet(cells, out_dir / "looks" / f"{look_id}.jpg", look["label"])
    if edit["look_id"] not in looks:
        lut_filter = resolve_look_filter(edit["look_id"], looks)
        cells = []
        for sequence, (_, labels) in enumerate(frames, 1):
            filtered = work / f"approved-lut-{sequence}.png"
            source = work / f"{sequence}.png"
            run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vf", lut_filter, "-frames:v", "1", str(filtered)], check=True)
            with Image.open(filtered) as opened:
                cells.append((opened.convert("RGB").copy(), ["Approved LUT", *labels]))
        _sheet(cells, out_dir / "looks" / "approved-lut.jpg", "Approved LUT")
    duration = max(timeline_duration(edit["timeline"]), 0.01)
    beat = Image.new("RGB", (1200, 180), "white")
    draw = ImageDraw.Draw(beat)
    draw.text((12, 10), "Beat map", fill="black", font=_font())
    axis_y, left, right = 95, 50, 1150
    draw.line((left, axis_y, right, axis_y), fill="black", width=2)
    for item in edit["timeline"]:
        x = left + (right - left) * float(item["cut_at"]) / duration
        color = "red" if item["beat_kind"] == "accent" else "blue"
        draw.line((x, axis_y - 35, x, axis_y + 35), fill=color, width=2)
        draw.text((x + 2, axis_y + 40), f"{item['cut_at']:.2f}s {item['beat_kind']}", fill="black", font=_font())
    if music_analysis is not None:
        validate_music_analysis(music_analysis, edit["music_id"])
    analysis = music_analysis or {}
    for beat_time in analysis.get("beats", []):
        if isinstance(beat_time, (int, float)) and 0 <= beat_time <= duration:
            x = left + (right - left) * float(beat_time) / duration
            draw.ellipse((x - 3, axis_y - 3, x + 3, axis_y + 3), fill="gray")
    for accent_time in analysis.get("accents", []):
        if isinstance(accent_time, (int, float)) and 0 <= accent_time <= duration:
            x = left + (right - left) * float(accent_time) / duration
            draw.polygon(((x, axis_y - 22), (x - 5, axis_y - 12), (x + 5, axis_y - 12)), fill="orange")
    for section in analysis.get("sections", []):
        if isinstance(section, dict) and isinstance(section.get("in"), (int, float)):
            x = left + (right - left) * max(0, min(duration, float(section["in"]))) / duration
            draw.line((x, axis_y - 50, x, axis_y - 42), fill="green", width=3)
            draw.text((x + 2, axis_y - 68), str(section.get("type", "section")), fill="green", font=_font())
    draw.text((left, 145), f"0s                                      {duration:.2f}s", fill="black", font=_font())
    beat.save(out_dir / "beat-map.jpg", quality=90)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--edit", required=True, type=Path)
    parser.add_argument("--looks", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--music-analysis", type=Path)
    args = parser.parse_args()
    analysis = load_json_object(args.music_analysis) if args.music_analysis else None
    render_proposal(load_json_object(args.library), load_json_object(args.edit), load_looks(args.looks), args.out_dir, music_analysis=analysis)


if __name__ == "__main__":
    main()
