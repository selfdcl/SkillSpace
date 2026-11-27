import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pipeline_common import sha256_file
from validate_pipeline import validate_bundle, validate_library_for_pipeline


class PipelineContractsTest(unittest.TestCase):
    def setUp(self):
        self.library = {
            "schema": "aerial-parts/v1",
            "created": "2026-08-22T00:00:00Z",
            "source_dir": "D:/source",
            "parts_dir": "D:/job/parts",
            "parts": [{
                "id": "p1", "src": "D:/source/a.mp4", "in": 1.0,
                "out": 5.0, "file": "D:/job/parts/p1.mp4", "dur": 4.0,
                "shot": "拉升", "subject": "海岸线", "light": "日落",
                "move": "由低到高", "quality": "可用", "note": "海岸揭示"
            }],
        }
        self.brief = {
            "schema": "aerial-brief/v1", "theme": "海边日落",
            "target_sec": 4, "platform": "小红书", "aspect": "9:16",
            "pace": "舒缓", "look_request": "暖金",
            "titles": False, "subtitles": False, "voiceover": False,
            "music": {"source": "local", "vocal": False, "commercial_required": True},
        }
        self.edit = {
            "schema": "aerial-edit/v2", "theme": "海边日落",
            "target_sec": 4, "aspect": "9:16", "look_id": "warm-gold",
            "music_id": "m1", "timeline": [{
                "part_id": "p1", "role": "opening", "source_in": 0.0,
                "source_out": 4.0, "cut_at": 0.0,
                "transition": "cut", "beat_kind": "downbeat",
            }],
            "titles": [], "captions": [], "graphics": [], "missing": [],
        }

    def test_valid_bundle_has_no_errors(self):
        self.assertEqual(validate_bundle(self.library, self.brief, self.edit), [])

    def test_unknown_part_is_rejected(self):
        self.edit["timeline"][0]["part_id"] = "missing"
        self.assertIn("timeline[0] unknown part_id: missing", validate_bundle(
            self.library, self.brief, self.edit
        ))

    def test_out_of_range_trim_is_rejected(self):
        self.edit["timeline"][0]["source_out"] = 4.5
        self.assertIn("timeline[0] source_out exceeds part duration", validate_bundle(
            self.library, self.brief, self.edit
        ))

    def test_approval_must_match_edit_hash(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = Path(td) / "edit.json"
            edit_path.write_text(json.dumps(self.edit), encoding="utf-8")
            approval = {
                "schema": "aerial-approval/v1", "status": "approved",
                "edit_sha256": "0" * 64, "look_id": "warm-gold",
                "music_id": "m1", "approved_at": "2026-08-22T00:00:00Z",
            }
            errors = validate_bundle(self.library, self.brief, self.edit, approval,
                                     edit_path=edit_path)
            self.assertIn("approval edit_sha256 does not match edit.json", errors)
            self.assertEqual(len(sha256_file(edit_path)), 64)

    def test_approval_requires_an_edit_path(self):
        approval = {
            "schema": "aerial-approval/v1", "status": "approved",
            "edit_sha256": "0" * 64, "look_id": "warm-gold",
            "music_id": "m1", "approved_at": "2026-08-22T00:00:00Z",
        }
        self.assertIn("approval requires edit_path", validate_bundle(
            self.library, self.brief, self.edit, approval
        ))

    def test_approval_requires_an_existing_edit_path(self):
        approval = {
            "schema": "aerial-approval/v1", "status": "approved",
            "edit_sha256": "0" * 64, "look_id": "warm-gold",
            "music_id": "m1", "approved_at": "2026-08-22T00:00:00Z",
        }
        self.assertIn("approval edit_path does not exist", validate_bundle(
            self.library, self.brief, self.edit, approval,
            edit_path=Path("does-not-exist.json"),
        ))

    def test_missing_overlay_arrays_are_rejected(self):
        del self.edit["titles"]
        del self.edit["captions"]
        del self.edit["graphics"]
        errors = validate_bundle(self.library, self.brief, self.edit)
        self.assertIn("edit missing required field: titles", errors)
        self.assertIn("edit missing required field: captions", errors)
        self.assertIn("edit missing required field: graphics", errors)

    def test_invalid_overlay_time_range_is_rejected(self):
        self.edit["titles"] = [{"text": "Sunset", "start_sec": 3, "end_sec": 3}]
        errors = validate_bundle(self.library, self.brief, self.edit)
        self.assertIn("titles[0] end_sec must be greater than start_sec", errors)

    def test_rejects_target_duration_mismatch_and_overlay_past_actual_timeline(self):
        self.edit["timeline"][0]["source_out"] = 3
        self.edit["titles"] = [{"text": "late", "start_sec": 2.5, "end_sec": 3.2}]
        errors = validate_bundle(self.library, self.brief, self.edit)
        self.assertIn("edit target_sec must match actual timeline duration within 0.5 seconds", errors)
        self.assertIn("titles[0] end_sec exceeds actual timeline duration", errors)

    def test_rejects_brief_and_edit_target_mismatch_even_when_timeline_matches_edit(self):
        self.brief["target_sec"] = 3
        errors = validate_bundle(self.library, self.brief, self.edit)
        self.assertIn("brief target_sec must match edit target_sec within 0.5 seconds", errors)

    def test_check_files_ignores_part_src(self):
        with tempfile.TemporaryDirectory() as td:
            part_file = Path(td) / "p1.mp4"
            part_file.write_bytes(b"part")
            self.library["parts"][0]["file"] = str(part_file)
            self.library["parts"][0]["src"] = str(Path(td) / "missing-source.mp4")
            self.assertEqual(
                validate_bundle(self.library, self.brief, self.edit, check_files=True), []
            )

    def test_part_src_is_not_required_by_new_pipeline_validation(self):
        with tempfile.TemporaryDirectory() as td:
            part_file = Path(td) / "p1.mp4"
            part_file.write_bytes(b"part")
            del self.library["parts"][0]["src"]
            self.library["parts"][0]["file"] = str(part_file)
            self.assertEqual(validate_bundle(self.library, self.brief, self.edit), [])
            self.assertEqual(
                validate_bundle(self.library, self.brief, self.edit, check_files=True), []
            )

    def test_rejects_extra_top_level_field(self):
        self.brief["unexpected"] = True
        self.assertIn("brief has unexpected field: unexpected", validate_bundle(
            self.library, self.brief, self.edit
        ))

    def test_rejects_wrong_brief_theme_type(self):
        self.brief["theme"] = 42
        self.assertIn("brief field must be a string: theme", validate_bundle(
            self.library, self.brief, self.edit
        ))

    def test_rejects_non_array_missing(self):
        self.edit["missing"] = "none"
        self.assertIn("edit field must be an array: missing", validate_bundle(
            self.library, self.brief, self.edit
        ))

    def test_rejects_invalid_timeline_role_and_cut_at(self):
        self.edit["timeline"][0]["role"] = 2
        self.edit["timeline"][0]["cut_at"] = -1
        errors = validate_bundle(self.library, self.brief, self.edit)
        self.assertIn("timeline[0] role must be a string", errors)
        self.assertIn("timeline[0] cut_at must be non-negative", errors)

    def test_unknown_part_keeps_independent_item_errors(self):
        item = self.edit["timeline"][0]
        item.update({
            "part_id": "missing", "source_in": "bad", "source_out": "bad",
            "transition": "wipe", "beat_kind": "pulse",
        })
        errors = validate_bundle(self.library, self.brief, self.edit)
        self.assertIn("timeline[0] unknown part_id: missing", errors)
        self.assertIn("timeline[0] source_in must be non-negative", errors)
        self.assertIn("timeline[0] source_out must be greater than zero", errors)
        self.assertIn("timeline[0] invalid transition", errors)
        self.assertIn("timeline[0] invalid beat_kind", errors)

    def test_rejects_malformed_library_part_duration(self):
        self.library["parts"][0]["dur"] = "four"
        self.assertIn("library parts[0] dur must be a positive number", validate_bundle(
            self.library, self.brief, self.edit
        ))

    def test_explicit_stabilize_is_accepted(self):
        self.edit["timeline"][0]["stabilize"] = True
        self.assertEqual(validate_bundle(self.library, self.brief, self.edit), [])

    def test_consumer_library_validation_ignores_missing_source_footage(self):
        with tempfile.TemporaryDirectory() as td:
            part_file = Path(td) / "p1.mp4"
            part_file.write_bytes(b"part")
            self.library["parts"][0]["file"] = str(part_file)
            self.library["parts"][0]["src"] = str(Path(td) / "missing-source.mp4")
            self.assertEqual(validate_library_for_pipeline(self.library, check_files=True), [])

    def test_consumer_library_validation_requires_part_file_but_not_src_field(self):
        del self.library["parts"][0]["src"]
        self.assertIn("part file does not exist", validate_library_for_pipeline(
            self.library, check_files=True
        )[0])

    def test_consumer_library_cli_accepts_library_without_bundle_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            part_file = root / "p1.mp4"
            part_file.write_bytes(b"part")
            self.library["parts"][0]["file"] = str(part_file)
            self.library["parts"][0]["src"] = str(root / "missing-source.mp4")
            library_path = root / "library.json"
            library_path.write_text(json.dumps(self.library), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_pipeline.py"), "--library", str(library_path), "--check-files"],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual((result.returncode, result.stdout.strip()), (0, "OK"))


if __name__ == "__main__":
    unittest.main()
