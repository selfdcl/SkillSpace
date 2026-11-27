"""Rank tracks from an on-disk aerial music library."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from pipeline_common import load_json_object, write_json_object


def validate_music_library(library: dict) -> None:
    """Fail closed unless the local music library matches aerial-music-library/v1."""
    if not isinstance(library, dict) or library.get("schema") != "aerial-music-library/v1":
        raise ValueError("music library schema must be aerial-music-library/v1")
    tracks = library.get("tracks")
    if not isinstance(tracks, list):
        raise ValueError("music library tracks must be an array")
    allowed = {"id", "file", "license", "title", "moods", "genres", "commercial", "bpm", "vocal"}
    ids: set[str] = set()
    for index, track in enumerate(tracks):
        name = f"music library tracks[{index}]"
        if not isinstance(track, dict):
            raise ValueError(f"{name} must be an object")
        if set(track) - allowed:
            raise ValueError(f"{name} has unexpected fields")
        for field in ("id", "file", "license"):
            if not isinstance(track.get(field), str) or not track[field].strip():
                raise ValueError(f"{name} {field} must be a non-empty string")
        if track["id"] in ids:
            raise ValueError(f"music library track IDs must be unique: {track['id']}")
        ids.add(track["id"])
        for field in ("title",):
            if field in track and not isinstance(track[field], str):
                raise ValueError(f"{name} {field} must be a string")
        for field in ("moods", "genres"):
            if field in track and (not isinstance(track[field], list) or any(not isinstance(item, str) for item in track[field])):
                raise ValueError(f"{name} {field} must be an array of strings")
        for field in ("commercial", "vocal"):
            if field in track and not isinstance(track[field], bool):
                raise ValueError(f"{name} {field} must be a boolean")
        if "bpm" in track and (not isinstance(track["bpm"], (int, float)) or isinstance(track["bpm"], bool) or not math.isfinite(float(track["bpm"])) or track["bpm"] <= 0):
            raise ValueError(f"{name} bpm must be a finite positive number")


def _values(value: object) -> set[str]:
    return {str(item) for item in value} if isinstance(value, list) else set()


def _score(track: dict, profile: dict) -> float:
    score = 4 * len(_values(track.get("moods")) & _values(profile.get("moods")))
    score += 2 * len(_values(track.get("genres")) & _values(profile.get("genres")))
    bpm = track.get("bpm")
    low, high = profile.get("bpm_min"), profile.get("bpm_max")
    numeric_values = (bpm, low, high)
    if all(isinstance(value, (int, float)) and not isinstance(value, bool)
           and math.isfinite(float(value)) for value in numeric_values):
        if low <= high:
            if low <= bpm <= high:
                score += 4
            else:
                score -= min(abs(bpm - low), abs(bpm - high)) / 10
    return float(score) if math.isfinite(float(score)) else 0.0


def search_music(library: dict, profile: dict) -> list[dict]:
    """Return hard-filtered local-library tracks in deterministic rank order."""
    validate_music_library(library)
    matches: list[dict] = []
    for raw_track in library.get("tracks", []):
        if not isinstance(raw_track, dict):
            continue
        if profile.get("commercial_required") is True and raw_track.get("commercial") is False:
            continue
        if "vocal" in profile and raw_track.get("vocal") != profile["vocal"]:
            continue
        track = dict(raw_track)
        track["score"] = _score(track, profile)
        matches.append(track)
    return sorted(matches, key=lambda track: (-track["score"], str(track.get("id", ""))))


def _is_readable_file(track: dict) -> bool:
    file_name = track.get("file")
    if not isinstance(file_name, str):
        return False
    try:
        with Path(file_name).open("rb"):
            return True
    except OSError:
        return False


def _resolve_track_file(track: dict, library_parent: Path) -> dict:
    normalized = dict(track)
    file_name = normalized.get("file")
    if isinstance(file_name, str):
        file_path = Path(file_name)
        normalized["file"] = str(
            (file_path if file_path.is_absolute() else library_parent / file_path).resolve()
        )
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank readable local music files.")
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    library = load_json_object(args.library)
    validate_music_library(library)
    profile = load_json_object(args.profile)
    library_parent = args.library.resolve().parent
    readable = [
        normalized for track in search_music(library, profile)
        if _is_readable_file(normalized := _resolve_track_file(track, library_parent))
    ]
    write_json_object(args.output, {
        "schema": "aerial-music-candidates/v1",
        "tracks": readable[:max(args.limit, 0)],
    })


if __name__ == "__main__":
    main()
