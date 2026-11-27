"""Validate aerial pipeline contracts with the Python standard library only."""
from __future__ import annotations

import argparse
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline_common import load_json_object, sha256_file

SCHEMAS = {"library": "aerial-parts/v1", "brief": "aerial-brief/v1", "edit": "aerial-edit/v2", "approval": "aerial-approval/v1"}
APPROVAL_HASH = re.compile(r"^[0-9a-f]{64}$")
ISO_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}T.+")


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _required(errors: list[str], value: object, name: str, fields: tuple[str, ...]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return False
    for field in fields:
        if field not in value:
            errors.append(f"{name} missing required field: {field}")
    return True


def _closed(errors: list[str], value: object, name: str, fields: tuple[str, ...]) -> None:
    if isinstance(value, dict):
        for field in value:
            if field not in fields:
                errors.append(f"{name} has unexpected field: {field}")


def _string(errors: list[str], value: dict, name: str, field: str, *, nonempty: bool = False) -> None:
    if field in value and not isinstance(value[field], str):
        errors.append(f"{name} field must be a string: {field}")
    elif nonempty and isinstance(value.get(field), str) and not value[field]:
        errors.append(f"{name} field must not be empty: {field}")


def _boolean(errors: list[str], value: dict, name: str, field: str) -> None:
    if field in value and not isinstance(value[field], bool):
        errors.append(f"{name} field must be a boolean: {field}")


def _positive_number(errors: list[str], value: dict, name: str, field: str, *, allow_zero: bool = False) -> None:
    if field in value and (not _number(value[field]) or (value[field] < 0 if allow_zero else value[field] <= 0)):
        errors.append(f"{name} {field} must be {'non-negative' if allow_zero else 'greater than zero'}")


def _timeline_actual_duration(timeline: object) -> float | None:
    if not isinstance(timeline, list) or not timeline:
        return None
    ends: list[float] = []
    for item in timeline:
        if not isinstance(item, dict):
            return None
        values = (item.get("cut_at"), item.get("source_in"), item.get("source_out"))
        if any(not _number(value) or not math.isfinite(float(value)) for value in values):
            return None
        cut_at, source_in, source_out = (float(value) for value in values)
        if source_out <= source_in or cut_at < 0:
            return None
        ends.append(cut_at + source_out - source_in)
    return max(ends)


def _validate_library(errors: list[str], library: object) -> dict[str, dict]:
    fields = ("schema", "created", "source_dir", "parts_dir", "parts")
    if not _required(errors, library, "library", fields):
        return {}
    assert isinstance(library, dict)
    if library.get("schema") != SCHEMAS["library"]:
        errors.append(f"library schema must be {SCHEMAS['library']}")
    for field in ("created", "source_dir", "parts_dir"):
        _string(errors, library, "library", field)
    if not isinstance(library.get("parts"), list):
        errors.append("library field must be an array: parts")
        return {}
    part_fields = ("id", "in", "out", "file", "dur", "shot", "subject", "light", "move", "quality", "note")
    part_by_id: dict[str, dict] = {}
    for index, part in enumerate(library["parts"]):
        name = f"library parts[{index}]"
        if not _required(errors, part, name, part_fields):
            continue
        assert isinstance(part, dict)
        for field in ("id", "file", "shot", "subject", "light", "move", "quality", "note"):
            _string(errors, part, name, field, nonempty=field in {"id", "subject"})
        _positive_number(errors, part, name, "in", allow_zero=True)
        _positive_number(errors, part, name, "out", allow_zero=True)
        duration = part.get("dur")
        if not _number(duration) or duration <= 0:
            errors.append(f"{name} dur must be a positive number")
        elif duration > 6.05:
            errors.append(f"{name} dur must not exceed 6.05")
        if part.get("shot") not in {"拉升", "环绕", "横移", "俯冲", "悬停", "未定"}:
            errors.append(f"{name} invalid shot")
        if part.get("light") not in {"日出", "日落", "晴", "阴", "夜景", "黄金时刻", "未定"}:
            errors.append(f"{name} invalid light")
        if part.get("quality") not in {"可用", "勉强"}:
            errors.append(f"{name} invalid quality")
        if isinstance(part.get("id"), str):
            part_by_id[part["id"]] = part
    return part_by_id


def validate_library_for_pipeline(library: dict, check_files: bool = False) -> list[str]:
    """Validate only the ingest contract consumed by proposal and editing stages.

    Pipeline consumers deliberately validate extracted ``parts[].file`` assets,
    not source-footage paths.  The ingest validator remains responsible for any
    source-footage checks during ingestion.
    """
    errors: list[str] = []
    part_by_id = _validate_library(errors, library)
    if check_files:
        for part in part_by_id.values():
            file_name = part.get("file")
            if not isinstance(file_name, str) or not Path(file_name).is_file():
                errors.append(f"part file does not exist: {file_name}")
    return errors


def _validate_brief(errors: list[str], brief: object) -> None:
    fields = ("schema", "theme", "target_sec", "platform", "aspect", "pace", "look_request", "titles", "subtitles", "voiceover", "music")
    if not _required(errors, brief, "brief", fields):
        return
    assert isinstance(brief, dict)
    _closed(errors, brief, "brief", fields)
    if brief.get("schema") != SCHEMAS["brief"]:
        errors.append(f"brief schema must be {SCHEMAS['brief']}")
    for field in ("theme", "platform", "aspect", "pace", "look_request"):
        _string(errors, brief, "brief", field, nonempty=True)
    _positive_number(errors, brief, "brief", "target_sec")
    for field in ("titles", "subtitles", "voiceover"):
        _boolean(errors, brief, "brief", field)
    music = brief.get("music")
    music_fields = ("source", "vocal", "commercial_required")
    if not _required(errors, music, "brief music", music_fields):
        return
    assert isinstance(music, dict)
    _closed(errors, music, "brief music", music_fields)
    _string(errors, music, "brief music", "source", nonempty=True)
    _boolean(errors, music, "brief music", "vocal")
    _boolean(errors, music, "brief music", "commercial_required")


def _validate_overlays(errors: list[str], edit: dict, actual_duration: float | None) -> None:
    for kind, fields in (("titles", ("text", "start_sec", "end_sec")), ("captions", ("text", "start_sec", "end_sec")), ("graphics", ("file", "start_sec", "end_sec", "position", "scale", "opacity"))):
        entries = edit.get(kind)
        if not isinstance(entries, list):
            if kind in edit:
                errors.append(f"edit field must be an array: {kind}")
            continue
        for index, entry in enumerate(entries):
            name = f"{kind}[{index}]"
            if not _required(errors, entry, name, fields):
                continue
            assert isinstance(entry, dict)
            _closed(errors, entry, name, fields + (("animated",) if kind == "titles" else ()))
            if kind == "graphics":
                _string(errors, entry, name, "file", nonempty=True)
                _string(errors, entry, name, "position", nonempty=True)
                _positive_number(errors, entry, name, "scale")
                if not _number(entry.get("opacity")) or not 0 <= entry["opacity"] <= 1:
                    errors.append(f"{name} opacity must be between zero and one")
            else:
                _string(errors, entry, name, "text")
                if kind == "titles" and "animated" in entry and not isinstance(entry["animated"], bool):
                    errors.append(f"{name} animated must be a boolean")
            start, end = entry.get("start_sec"), entry.get("end_sec")
            if not _number(start) or not _number(end):
                errors.append(f"{name} start_sec and end_sec must be numeric")
            elif end <= start:
                errors.append(f"{name} end_sec must be greater than start_sec")
            elif start < 0:
                errors.append(f"{name} start_sec must be non-negative")
            elif actual_duration is not None and end > actual_duration + 1e-6:
                errors.append(f"{name} end_sec exceeds actual timeline duration")


def _validate_edit(errors: list[str], edit: object, part_by_id: dict[str, dict]) -> None:
    fields = ("schema", "theme", "target_sec", "aspect", "look_id", "music_id", "timeline", "titles", "captions", "graphics", "missing")
    if not _required(errors, edit, "edit", fields):
        return
    assert isinstance(edit, dict)
    _closed(errors, edit, "edit", fields)
    if edit.get("schema") != SCHEMAS["edit"]:
        errors.append(f"edit schema must be {SCHEMAS['edit']}")
    for field in ("theme", "aspect", "look_id", "music_id"):
        _string(errors, edit, "edit", field, nonempty=True)
    _positive_number(errors, edit, "edit", "target_sec")
    if not isinstance(edit.get("missing"), list):
        errors.append("edit field must be an array: missing")
    timeline = edit.get("timeline")
    if not isinstance(timeline, list):
        errors.append("edit field must be an array: timeline")
    else:
        item_fields = ("part_id", "role", "source_in", "source_out", "cut_at", "transition", "beat_kind")
        for index, item in enumerate(timeline):
            name = f"timeline[{index}]"
            if not _required(errors, item, name, item_fields):
                continue
            assert isinstance(item, dict)
            _closed(errors, item, name, item_fields + ("stabilize",))
            _string(errors, item, name, "part_id", nonempty=True)
            if not isinstance(item.get("role"), str):
                errors.append(f"{name} role must be a string")
            elif not item["role"]:
                errors.append(f"{name} role must not be empty")
            _positive_number(errors, item, name, "source_in", allow_zero=True)
            _positive_number(errors, item, name, "source_out")
            _positive_number(errors, item, name, "cut_at", allow_zero=True)
            if item.get("transition") not in {"cut", "fade", "fade-black"}:
                errors.append(f"{name} invalid transition")
            if item.get("beat_kind") not in {"none", "beat", "downbeat", "accent"}:
                errors.append(f"{name} invalid beat_kind")
            if "stabilize" in item and not isinstance(item["stabilize"], bool):
                errors.append(f"{name} stabilize must be a boolean")
            part_id = item.get("part_id")
            part = part_by_id.get(part_id) if isinstance(part_id, str) else None
            if part is None:
                errors.append(f"{name} unknown part_id: {part_id}")
            else:
                source_in, source_out = item.get("source_in"), item.get("source_out")
                if _number(source_out) and _number(part.get("dur")) and source_out > part["dur"]:
                    errors.append(f"{name} source_out exceeds part duration")
                if _number(source_in) and _number(source_out) and source_out <= source_in:
                    errors.append(f"{name} source_out must be greater than source_in")
    actual_duration = _timeline_actual_duration(timeline)
    if actual_duration is not None and _number(edit.get("target_sec")) and abs(float(edit["target_sec"]) - actual_duration) > 0.5:
        errors.append("edit target_sec must match actual timeline duration within 0.5 seconds")
    _validate_overlays(errors, edit, actual_duration)


def _validate_approval(errors: list[str], approval: object, edit: object, edit_path: Path | None) -> None:
    required = ("schema", "status", "edit_sha256", "look_id", "look_sha256", "music_id", "music_sha256", "approved_at")
    if not _required(errors, approval, "approval", required):
        return
    assert isinstance(approval, dict)
    _closed(errors, approval, "approval", required + ("note",))
    if approval.get("schema") != SCHEMAS["approval"]:
        errors.append(f"approval schema must be {SCHEMAS['approval']}")
    if approval.get("status") != "approved":
        errors.append("approval status must be approved")
    for field in ("edit_sha256", "look_id", "look_sha256", "music_id", "music_sha256", "approved_at"):
        _string(errors, approval, "approval", field, nonempty=True)
    if "note" in approval:
        _string(errors, approval, "approval", "note")
    edit_hash = approval.get("edit_sha256")
    if not isinstance(edit_hash, str) or not APPROVAL_HASH.fullmatch(edit_hash):
        errors.append("approval edit_sha256 must be 64 lowercase hexadecimal characters")
    for field in ("look_sha256", "music_sha256"):
        if not isinstance(approval.get(field), str) or not APPROVAL_HASH.fullmatch(approval[field]):
            errors.append(f"approval {field} must be 64 lowercase hexadecimal characters")
    approved_at = approval.get("approved_at")
    try:
        parsed_at = datetime.fromisoformat(approved_at.replace("Z", "+00:00")) if isinstance(approved_at, str) else None
    except ValueError:
        parsed_at = None
    if parsed_at is None or parsed_at.tzinfo is None or parsed_at.utcoffset() != timezone.utc.utcoffset(parsed_at):
        errors.append("approval approved_at must be ISO-8601 UTC")
    if isinstance(edit, dict) and approval.get("look_id") != edit.get("look_id"):
        errors.append("approval look_id does not match edit")
    if isinstance(edit, dict) and approval.get("music_id") != edit.get("music_id"):
        errors.append("approval music_id does not match edit")
    if edit_path is None:
        errors.append("approval requires edit_path")
    elif not Path(edit_path).is_file():
        errors.append("approval edit_path does not exist")
    elif edit_hash != sha256_file(edit_path):
        errors.append("approval edit_sha256 does not match edit.json")


def validate_bundle(library: dict, brief: dict, edit: dict, approval: dict | None = None, *, edit_path: Path | None = None, check_files: bool = False) -> list[str]:
    """Return every deterministic validation error; never stop at the first error."""
    errors: list[str] = []
    part_by_id = _validate_library(errors, library)
    _validate_brief(errors, brief)
    _validate_edit(errors, edit, part_by_id)
    if isinstance(brief, dict) and isinstance(edit, dict) and _number(brief.get("target_sec")) and _number(edit.get("target_sec")) and abs(float(brief["target_sec"]) - float(edit["target_sec"])) > 0.5:
        errors.append("brief target_sec must match edit target_sec within 0.5 seconds")
    if approval is not None:
        _validate_approval(errors, approval, edit, edit_path)
    if check_files:
        for part in part_by_id.values():
            file_name = part.get("file")
            if not isinstance(file_name, str) or not Path(file_name).is_file():
                errors.append(f"part file does not exist: {file_name}")
        if isinstance(edit, dict) and isinstance(edit.get("graphics"), list):
            for index, graphic in enumerate(edit["graphics"]):
                if isinstance(graphic, dict) and isinstance(graphic.get("file"), str) and not Path(graphic["file"]).is_file():
                    errors.append(f"graphics[{index}] file does not exist: {graphic['file']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate aerial pipeline contracts")
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--brief", type=Path)
    parser.add_argument("--edit", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--check-files", action="store_true")
    args = parser.parse_args()
    if (args.brief is None) != (args.edit is None):
        parser.error("--brief and --edit must be supplied together")
    if args.approval is not None and args.edit is None:
        parser.error("--approval requires --edit")
    library = load_json_object(args.library)
    if args.edit is None:
        errors = validate_library_for_pipeline(library, check_files=args.check_files)
    else:
        approval = load_json_object(args.approval) if args.approval else None
        errors = validate_bundle(library, load_json_object(args.brief), load_json_object(args.edit), approval, edit_path=args.edit, check_files=args.check_files)
    if not errors:
        print("OK")
        return 0
    print("\n".join(errors))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
