import sys
import os
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_ffmpeg import _stabilization_filter, ffmpeg_filter_escape, look_sha256, needs_remotion, require_approved, validate_master_timeline
from render_remotion import build_render_props, render_remotion


class RenderFfmpegTest(unittest.TestCase):
    def test_windows_lut_path_is_filter_escaped(self):
        self.assertEqual(ffmpeg_filter_escape(Path("D:/LUT/My Look.cube")), "D\\:/LUT/My\\ Look.cube")

    def test_rejects_unapproved_status(self):
        with self.assertRaisesRegex(ValueError, "status must be approved"):
            require_approved({"status": "draft"}, "a" * 64, "warm-gold", "m1", "b" * 64, "c" * 64)

    def test_rejects_matching_ids_with_different_asset_hashes(self):
        approval = {"status": "approved", "edit_sha256": "a" * 64, "look_id": "warm-gold", "music_id": "m1", "music_sha256": "b" * 64, "look_sha256": "c" * 64}
        with self.assertRaisesRegex(ValueError, "music_sha256"):
            require_approved(approval, "a" * 64, "warm-gold", "m1", "d" * 64, "c" * 64)

    def test_timeline_rejects_gap_and_invalid_fade_black_overlap(self):
        with self.assertRaisesRegex(ValueError, "continuous"):
            validate_master_timeline([{"source_in": 0, "source_out": 1, "cut_at": 0, "transition": "cut"}, {"source_in": 0, "source_out": 1, "cut_at": 1.1, "transition": "cut"}])
        with self.assertRaisesRegex(ValueError, "fade-black"):
            validate_master_timeline([{"source_in": 0, "source_out": 1, "cut_at": 0, "transition": "cut"}, {"source_in": 0, "source_out": 1, "cut_at": .75, "transition": "fade-black"}])

    def test_fade_black_requires_both_adjacent_clips_to_be_long_enough(self):
        with self.assertRaisesRegex(ValueError, "fade-black requires"):
            validate_master_timeline([{"source_in": 0, "source_out": .2, "cut_at": 0, "transition": "cut"}, {"source_in": 0, "source_out": 1, "cut_at": .2, "transition": "fade-black"}])
        with self.assertRaisesRegex(ValueError, "fade-black requires"):
            validate_master_timeline([{"source_in": 0, "source_out": 1, "cut_at": 0, "transition": "cut"}, {"source_in": 0, "source_out": .2, "cut_at": 1, "transition": "fade-black"}])

    def test_fade_transitions_check_immediately_previous_clip_not_cumulative_tail(self):
        for transition in ("fade", "fade-black"):
            with self.assertRaisesRegex(ValueError, transition):
                validate_master_timeline([{"source_in": 0, "source_out": 1, "cut_at": 0, "transition": "cut"}, {"source_in": 0, "source_out": .1, "cut_at": 1, "transition": "cut"}, {"source_in": 0, "source_out": 1, "cut_at": 1.1 if transition == "fade-black" else .85, "transition": transition}])

    def test_builtin_look_hash_is_stable(self):
        self.assertEqual(look_sha256("natural", {"natural": {"vf": "eq=contrast=1.03:saturation=1.05:gamma=1.01", "id": "natural", "label": "自然"}}), look_sha256("natural", {"natural": {"label": "自然", "id": "natural", "vf": "eq=contrast=1.03:saturation=1.05:gamma=1.01"}}))

    def test_stabilization_uses_timeline_index_not_untrusted_part_id_for_transform_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = []
            import render_ffmpeg
            original = render_ffmpeg.run_command
            render_ffmpeg.run_command = lambda command, **_kwargs: commands.append(command)
            try:
                value = _stabilization_filter(
                    {"stabilize": True, "source_in": 0, "source_out": 1},
                    {"id": "../x", "file": str(root / "part.mp4")}, 0, root / "work", "ffmpeg",
                )
            finally:
                render_ffmpeg.run_command = original
            transform = (root / "work" / "stabilization" / "clip-0001.trf").resolve()
            self.assertTrue(transform.parent.is_relative_to((root / "work" / "stabilization").resolve()))
            self.assertIn(ffmpeg_filter_escape(transform), value)
            self.assertNotIn("../x", " ".join(map(str, commands[0])))

    def test_simple_edit_does_not_need_remotion(self):
        self.assertFalse(needs_remotion({"titles": [], "captions": [], "graphics": []}))

    def test_graphics_enable_remotion(self):
        self.assertTrue(needs_remotion({"titles": [], "captions": [], "graphics": [{"file": "logo.png"}]}))

    def test_animated_title_enables_remotion(self):
        self.assertTrue(needs_remotion({"titles": [{"animated": True}], "captions": [], "graphics": []}))

    def test_remotion_refuses_to_render_without_explicit_license_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "base.mp4"
            base.write_bytes(b"base")
            previous = os.environ.pop("REMOTION_LICENSE_KEY", None)
            try:
                with self.assertRaisesRegex(ValueError, "REMOTION_LICENSE_KEY"):
                    render_remotion(base, {"timeline": [{"cut_at": 0, "source_in": 0, "source_out": 1}], "target_sec": 1, "aspect": "16:9", "titles": [], "captions": [], "graphics": []}, root / "assets", root / "props.json", root / "preview.mp4")
            finally:
                if previous is not None:
                    os.environ["REMOTION_LICENSE_KEY"] = previous

    def test_remotion_props_exclude_static_titles(self):
        props = build_render_props({"timeline": [{"cut_at": 0, "source_in": 0, "source_out": 1}], "aspect": "16:9", "titles": [{"text": "static", "start_sec": 0, "end_sec": 1}, {"text": "animated", "start_sec": 0, "end_sec": 1, "animated": True}], "captions": [], "graphics": []}, "base.mp4")
        self.assertEqual([title["text"] for title in props["titles"]], ["animated"])


if __name__ == "__main__":
    unittest.main()
