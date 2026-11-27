import csv
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pipeline_common import sha256_file
import publish_delivery
from publish_delivery import publish


class DeliveryTest(unittest.TestCase):
    def _report(self, preview: Path, *, edit_hash: str = "a" * 64) -> Path:
        report = preview.with_name("edit-report.json")
        report.write_text(json.dumps({
            "schema": "aerial-edit-report/v1", "preview_sha256": sha256_file(preview),
            "edit_sha256": edit_hash, "look_id": "warm-gold", "look_sha256": "b" * 64,
            "renderer": "ffmpeg", "part_ids": ["p1"],
        }), encoding="utf-8")
        return report

    def test_rejects_without_user_confirmation(self):
        with self.assertRaisesRegex(ValueError, "user confirmation required"):
            publish(Path("preview.mp4"), Path("report.json"), Path("out"), user_confirmed=False)

    def test_rejects_report_preview_hash_mismatch_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"video-fixture")
            report = self._report(preview)
            data = json.loads(report.read_text(encoding="utf-8"))
            data["preview_sha256"] = "0" * 64
            report.write_text(json.dumps(data), encoding="utf-8")
            output = root / "output"
            with self.assertRaisesRegex(ValueError, "preview_sha256"):
                publish(preview, report, output, user_confirmed=True)
            self.assertFalse(output.exists())

    def test_rejects_malformed_required_report_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"video")
            report = self._report(preview)
            for field, value in (("edit_sha256", "not-a-hash"), ("look_sha256", "not-a-hash"), ("renderer", "other"), ("preview_sha256", "A" * 64)):
                data = json.loads(report.read_text(encoding="utf-8"))
                data[field] = value
                report.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    publish(preview, report, root / "output", user_confirmed=True)
                self.assertFalse((root / "output").exists())
                report = self._report(preview)

    def test_cli_requires_literal_user_confirmed_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"video")
            result = subprocess.run([sys.executable, str(SCRIPTS / "publish_delivery.py"), "--preview", str(preview),
                                     "--report", str(self._report(preview)), "--output-dir", str(root / "output")],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "output").exists())

    def test_rejects_handoff_output_path_overlap_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"video")
            output = root / "output"
            with self.assertRaisesRegex(ValueError, "handoff.*overlap"):
                publish(preview, self._report(preview), output, user_confirmed=True, jianying=True,
                        handoff_dir=output)
            self.assertFalse(output.exists())

    def test_confirmed_publish_preserves_bytes_hash_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"video-fixture")
            final = publish(preview, self._report(preview), root / "output", user_confirmed=True)
            manifest = json.loads((root / "output" / "delivery-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(preview.read_bytes(), final.read_bytes())
            self.assertEqual(manifest["final_sha256"], sha256_file(final))
            self.assertEqual(manifest["edit_sha256"], "a" * 64)
            self.assertEqual(manifest["renderer"], "ffmpeg")
            self.assertTrue(manifest["published_at"])
            self.assertIn("final.mp4", manifest["files"])

    def test_republish_archives_previous_final_before_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"new-video")
            output = root / "output"
            output.mkdir()
            (output / "final.mp4").write_bytes(b"old-video")
            publish(preview, self._report(preview), output, user_confirmed=True)
            archived = list(output.glob("final.previous-*.mp4"))
            self.assertEqual((output / "final.mp4").read_bytes(), b"new-video")
            self.assertEqual([item.read_bytes() for item in archived], [b"old-video"])

    def test_staging_manifest_failure_preserves_existing_final_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"new-video")
            output = root / "output"
            output.mkdir()
            (output / "final.mp4").write_bytes(b"old-video")
            (output / "delivery-manifest.json").write_text('{"old": true}', encoding="utf-8")
            with mock.patch.object(publish_delivery, "write_json_object", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    publish(preview, self._report(preview), output, user_confirmed=True)
            self.assertEqual((output / "final.mp4").read_bytes(), b"old-video")
            self.assertEqual((output / "delivery-manifest.json").read_text(encoding="utf-8"), '{"old": true}')

    def test_commit_replace_failure_rolls_back_final_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = root / "preview.mp4"
            preview.write_bytes(b"new-video")
            output = root / "output"
            output.mkdir()
            (output / "final.mp4").write_bytes(b"old-video")
            (output / "delivery-manifest.json").write_text('{"old": true}', encoding="utf-8")
            real_replace = publish_delivery.os.replace
            failed = False
            def fail_manifest_replace(source, target):
                nonlocal failed
                if not failed and Path(target) == output / "delivery-manifest.json":
                    failed = True
                    raise OSError("replace failed")
                return real_replace(source, target)
            with mock.patch.object(publish_delivery.os, "replace", side_effect=fail_manifest_replace):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    publish(preview, self._report(preview), output, user_confirmed=True)
            self.assertEqual((output / "final.mp4").read_bytes(), b"old-video")
            self.assertEqual((output / "delivery-manifest.json").read_text(encoding="utf-8"), '{"old": true}')

    def test_final_archive_failure_keeps_both_old_delivery_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); preview = root / "preview.mp4"; preview.write_bytes(b"new")
            output = root / "output"; output.mkdir()
            (output / "final.mp4").write_bytes(b"old-final"); (output / "delivery-manifest.json").write_bytes(b"old-manifest")
            real = publish_delivery.os.replace; failed = False
            def fail_first_archive(source, target):
                nonlocal failed
                if not failed and Path(source) == output / "final.mp4" and ".previous-" in Path(target).name:
                    failed = True; raise OSError("archive final failed")
                return real(source, target)
            with mock.patch.object(publish_delivery.os, "replace", side_effect=fail_first_archive):
                with self.assertRaisesRegex(OSError, "archive final failed"):
                    publish(preview, self._report(preview), output, user_confirmed=True)
            self.assertEqual((output / "final.mp4").read_bytes(), b"old-final")
            self.assertEqual((output / "delivery-manifest.json").read_bytes(), b"old-manifest")
            self.assertFalse(list(root.glob(".output.delivery-staging-*")))

    def test_manifest_archive_failure_restores_final_without_touching_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); preview = root / "preview.mp4"; preview.write_bytes(b"new")
            output = root / "output"; output.mkdir()
            (output / "final.mp4").write_bytes(b"old-final"); (output / "delivery-manifest.json").write_bytes(b"old-manifest")
            real = publish_delivery.os.replace; failed = False
            def fail_manifest_archive(source, target):
                nonlocal failed
                if not failed and Path(source) == output / "delivery-manifest.json" and ".previous-" in Path(target).name:
                    failed = True; raise OSError("archive manifest failed")
                return real(source, target)
            with mock.patch.object(publish_delivery.os, "replace", side_effect=fail_manifest_archive):
                with self.assertRaisesRegex(OSError, "archive manifest failed"):
                    publish(preview, self._report(preview), output, user_confirmed=True)
            self.assertEqual((output / "final.mp4").read_bytes(), b"old-final")
            self.assertEqual((output / "delivery-manifest.json").read_bytes(), b"old-manifest")
            self.assertFalse(list(root.glob(".output.delivery-staging-*")))

    def test_final_install_failure_restores_both_old_delivery_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); preview = root / "preview.mp4"; preview.write_bytes(b"new")
            output = root / "output"; output.mkdir()
            (output / "final.mp4").write_bytes(b"old-final"); (output / "delivery-manifest.json").write_bytes(b"old-manifest")
            real = publish_delivery.os.replace; failed = False
            def fail_final_install(source, target):
                nonlocal failed
                if not failed and Path(target) == output / "final.mp4" and ".delivery-staging-" in str(source):
                    failed = True; raise OSError("install final failed")
                return real(source, target)
            with mock.patch.object(publish_delivery.os, "replace", side_effect=fail_final_install):
                with self.assertRaisesRegex(OSError, "install final failed"):
                    publish(preview, self._report(preview), output, user_confirmed=True)
            self.assertEqual((output / "final.mp4").read_bytes(), b"old-final")
            self.assertEqual((output / "delivery-manifest.json").read_bytes(), b"old-manifest")
            self.assertFalse(list(root.glob(".output.delivery-staging-*")))

    def test_jianying_handoff_copies_only_timeline_part_files_and_utf8_bom_csv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview, part_one, unused, music = (root / name for name in ("preview.mp4", "part-one.mp4", "unused.mp4", "music.wav"))
            preview.write_bytes(b"preview")
            part_one.write_bytes(b"part-one")
            unused.write_bytes(b"unused")
            music.write_bytes(b"music")
            subtitle, cube, storyboard = root / "captions.srt", root / "look.cube", root / "storyboard.jpg"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\n字幕\n", encoding="utf-8")
            cube.write_text("TITLE look", encoding="utf-8")
            storyboard.write_bytes(b"story")
            library = root / "library.json"
            library.write_text(json.dumps({"parts": [
                {"id": "p1", "file": str(part_one), "src": "must-not-be-read"},
                {"id": "p2", "file": str(unused), "src": "must-not-be-read"},
            ]}), encoding="utf-8")
            edit = root / "edit.json"
            edit.write_text(json.dumps({"look_id": str(cube), "timeline": [
                {"part_id": "p1", "source_in": 0, "source_out": 1, "cut_at": 0, "transition": "cut"},
                {"part_id": "p1", "source_in": 1, "source_out": 2, "cut_at": 1, "transition": "cut"},
            ]}), encoding="utf-8")
            output = root / "output"
            report = self._report(preview, edit_hash=sha256_file(edit))
            report_data = json.loads(report.read_text(encoding="utf-8"))
            report_data.update({"look_id": str(cube), "look_sha256": sha256_file(cube)})
            report.write_text(json.dumps(report_data), encoding="utf-8")
            publish(preview, report, output, user_confirmed=True, jianying=True,
                    library_path=library, edit_path=edit, music_path=music, subtitle_path=subtitle,
                    cube_path=cube, storyboard_path=storyboard)
            handoff = root / "handoff-jianying"
            self.assertEqual((handoff / "video" / "part-one.mp4").read_bytes(), b"part-one")
            self.assertFalse((handoff / "video" / "unused.mp4").exists())
            self.assertEqual((handoff / "audio" / "music.wav").read_bytes(), b"music")
            self.assertEqual((handoff / "subtitles" / "captions.srt").read_text(encoding="utf-8"), subtitle.read_text(encoding="utf-8"))
            self.assertEqual((handoff / "lut" / "look.cube").read_text(encoding="utf-8"), "TITLE look")
            self.assertTrue((handoff / "README.md").is_file())
            self.assertIn("不是剪映原生草稿", (handoff / "README.md").read_text(encoding="utf-8"))
            raw = (handoff / "edit-list.csv").read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
            self.assertEqual([row["part_id"] for row in rows], ["p1", "p1"])
            self.assertEqual([(row["source_in"], row["source_out"], row["cut_at"], row["transition"]) for row in rows],
                             [("0", "1", "0", "cut"), ("1", "2", "1", "cut")])
            self.assertEqual(len(list((handoff / "video").iterdir())), 1)
            self.assertTrue((handoff / "storyboard.jpg").is_file())

    def test_custom_edit_lut_is_hash_bound_and_copied_without_cube_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview, part, music, cube = (root / name for name in ("preview.mp4", "part.mp4", "music.wav", "approved.cube"))
            for path in (preview, part, music): path.write_bytes(b"asset")
            cube.write_text("TITLE approved", encoding="utf-8")
            library = root / "library.json"; library.write_text(json.dumps({"parts": [{"id": "p1", "file": str(part)}]}), encoding="utf-8")
            edit = root / "edit.json"; edit.write_text(json.dumps({"look_id": str(cube), "timeline": [{"part_id": "p1"}]}), encoding="utf-8")
            report = self._report(preview, edit_hash=sha256_file(edit))
            data = json.loads(report.read_text(encoding="utf-8")); data.update({"look_id": str(cube), "look_sha256": sha256_file(cube)}); report.write_text(json.dumps(data), encoding="utf-8")
            publish(preview, report, root / "output", user_confirmed=True, jianying=True, library_path=library, edit_path=edit, music_path=music)
            self.assertEqual((root / "handoff-jianying" / "lut" / "approved.cube").read_text(encoding="utf-8"), "TITLE approved")

    def test_jianying_rejects_wrong_or_extra_cube_for_selected_look(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); preview, part, music, cube, wrong = (root / name for name in ("preview.mp4", "part.mp4", "music.wav", "approved.cube", "wrong.cube"))
            for path in (preview, part, music, cube, wrong): path.write_bytes(b"asset")
            library = root / "library.json"; library.write_text(json.dumps({"parts": [{"id": "p1", "file": str(part)}]}), encoding="utf-8")
            edit = root / "edit.json"; edit.write_text(json.dumps({"look_id": str(cube), "timeline": [{"part_id": "p1"}]}), encoding="utf-8")
            report = self._report(preview, edit_hash=sha256_file(edit)); data = json.loads(report.read_text(encoding="utf-8")); data.update({"look_id": str(cube), "look_sha256": sha256_file(cube)}); report.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cube"):
                publish(preview, report, root / "output", user_confirmed=True, jianying=True, library_path=library, edit_path=edit, music_path=music, cube_path=wrong)
            builtin = root / "builtin.json"; builtin.write_text(json.dumps({"look_id": "warm-gold", "timeline": [{"part_id": "p1"}]}), encoding="utf-8")
            builtin_report = self._report(preview, edit_hash=sha256_file(builtin))
            with self.assertRaisesRegex(ValueError, "built-in"):
                publish(preview, builtin_report, root / "output", user_confirmed=True, jianying=True, library_path=library, edit_path=builtin, music_path=music, cube_path=cube)

    def test_jianying_rejects_missing_selected_custom_cube_before_delivery_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); preview, part, music, cube = (root / name for name in ("preview.mp4", "part.mp4", "music.wav", "missing.cube"))
            for path in (preview, part, music): path.write_bytes(b"asset")
            library = root / "library.json"; library.write_text(json.dumps({"parts": [{"id": "p1", "file": str(part)}]}), encoding="utf-8")
            edit = root / "edit.json"; edit.write_text(json.dumps({"look_id": str(cube), "timeline": [{"part_id": "p1"}]}), encoding="utf-8")
            report = self._report(preview, edit_hash=sha256_file(edit)); data = json.loads(report.read_text(encoding="utf-8")); data.update({"look_id": str(cube), "look_sha256": "a" * 64}); report.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved LUT"):
                publish(preview, report, root / "output", user_confirmed=True, jianying=True, library_path=library, edit_path=edit, music_path=music)
            self.assertFalse((root / "output").exists())

    def test_handoff_rejects_same_basename_from_different_used_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            one, two, music, preview = root / "one" / "same.mp4", root / "two" / "same.mp4", root / "music.wav", root / "preview.mp4"
            one.parent.mkdir(); two.parent.mkdir()
            one.write_bytes(b"one"); two.write_bytes(b"two"); music.write_bytes(b"music"); preview.write_bytes(b"preview")
            library, edit = root / "library.json", root / "edit.json"
            library.write_text(json.dumps({"parts": [{"id": "one", "file": str(one)}, {"id": "two", "file": str(two)}]}), encoding="utf-8")
            edit.write_text(json.dumps({"look_id": "warm-gold", "timeline": [{"part_id": "one"}, {"part_id": "two"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "filenames"):
                publish(preview, self._report(preview, edit_hash=sha256_file(edit)), root / "output", user_confirmed=True,
                        jianying=True, library_path=library, edit_path=edit, music_path=music)
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
