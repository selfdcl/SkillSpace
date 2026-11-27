import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_proposal import load_looks, render_proposal, representative_time, timeline_duration, validate_music_analysis
from render_rhythm_preview import build_rhythm_command, preview_geometry, render_rhythm_preview, validate_timeline


def library_for(part_file: Path, source: str = "D:/private/original.mp4") -> dict:
    return {
        "schema": "aerial-parts/v1", "created": "2026-08-22T00:00:00Z",
        "source_dir": "D:/source", "parts_dir": str(part_file.parent),
        "parts": [{"id": "p1", "src": source, "in": 1, "out": 3,
                   "file": str(part_file), "dur": 2, "shot": "拉升",
                   "subject": "海岸线", "light": "日落", "move": "上升",
                   "quality": "可用", "note": "揭示"}],
    }


def edit_for(part_id: str = "p1") -> dict:
    return {
        "schema": "aerial-edit/v2", "theme": "日落", "target_sec": 2,
        "aspect": "16:9", "look_id": "natural", "music_id": "m1",
        "timeline": [{"part_id": part_id, "role": "opening", "source_in": 0,
                      "source_out": 2, "cut_at": 0, "transition": "cut",
                      "beat_kind": "downbeat"}],
        "titles": [], "captions": [], "graphics": [], "missing": [],
    }


class ProposalTest(unittest.TestCase):
    def test_midpoint_selection_uses_relative_trim(self):
        self.assertEqual(representative_time(0.2, 1.4), 0.8)

    def test_looks_have_exact_required_ids(self):
        looks = load_looks(Path(__file__).resolve().parents[1] / "looks.json")
        self.assertEqual(list(looks), ["natural", "warm-gold", "teal-orange"])

    def test_timeline_duration_uses_cut_positions(self):
        timeline = [
            {"cut_at": 0, "source_in": 0, "source_out": 1.2},
            {"cut_at": 1.2, "source_in": 0.1, "source_out": 2.1},
        ]
        self.assertEqual(timeline_duration(timeline), 3.2)

    def test_command_rejects_unknown_part(self):
        with self.assertRaisesRegex(ValueError, "unknown part_id: missing"):
            build_rhythm_command(library_for(Path("p1.mp4")), edit_for("missing"), {},
                                 "ffmpeg", Path("out.mp4"), None)

    def test_command_uses_part_file_not_library_source(self):
        part = Path("D:/render-parts/p1.mp4")
        source = "D:/secret/raw-original.mp4"
        with tempfile.TemporaryDirectory() as temporary:
            music = Path(temporary) / "music.wav"
            music.write_bytes(b"audio")
            command = build_rhythm_command(library_for(part, source), edit_for(), {"natural": {"vf": "null"}}, "ffmpeg",
                                           Path("D:/out/rhythm-preview.mp4"), music)
        self.assertIn(str(part), command)
        self.assertNotIn(source, command)

    def test_rhythm_preview_accepts_readable_custom_cube_and_escapes_its_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            music, cube = root / "music.wav", root / "custom look.cube"
            music.write_bytes(b"audio")
            cube.write_text("TITLE custom", encoding="utf-8")
            edit = edit_for()
            edit["look_id"] = str(cube)
            command = build_rhythm_command(library_for(Path("p1.mp4")), edit, {"natural": {"vf": "null"}}, "ffmpeg", root / "out.mp4", music)
        self.assertIn("lut3d=file='", " ".join(command))
        self.assertIn("custom\\ look.cube", " ".join(command))

    def test_rhythm_preview_rejects_non_cube_and_unreadable_custom_looks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            music = root / "music.wav"
            music.write_bytes(b"audio")
            for candidate in (root / "not-a-lut.txt", root / "missing.cube"):
                edit = edit_for()
                edit["look_id"] = str(candidate)
                with self.assertRaisesRegex(ValueError, "unreadable"):
                    build_rhythm_command(library_for(Path("p1.mp4")), edit, {"natural": {"vf": "null"}}, "ffmpeg", root / "out.mp4", music)

    def test_preview_geometry_respects_edit_aspect(self):
        self.assertEqual(preview_geometry("16:9"), (1280, 720))
        self.assertEqual(preview_geometry("9:16"), (720, 1280))
        with self.assertRaisesRegex(ValueError, "unsupported aspect"):
            preview_geometry("1:1")

    def test_timeline_rejects_gap_and_bad_fade_offset(self):
        first = {"source_in": 0, "source_out": 1, "cut_at": 0, "transition": "cut"}
        with self.assertRaisesRegex(ValueError, "continuous"):
            validate_timeline([first, {"source_in": 0, "source_out": 1, "cut_at": 1.1, "transition": "cut"}])
        with self.assertRaisesRegex(ValueError, "continuous"):
            validate_timeline([first, {"source_in": 0, "source_out": 1, "cut_at": 1, "transition": "fade"}])
        with self.assertRaisesRegex(ValueError, "transition"):
            validate_timeline([first, {"source_in": 0, "source_out": 1, "cut_at": 1, "transition": "fade-black"}])

    def test_preview_requires_readable_music(self):
        with self.assertRaisesRegex(ValueError, "music file"):
            build_rhythm_command(library_for(Path("p1.mp4")), edit_for(), {"natural": {"vf": "null"}},
                                 "ffmpeg", Path("out.mp4"), None)

    def test_music_analysis_fails_closed_when_schema_id_or_timestamps_are_invalid(self):
        valid = {"schema": "aerial-music-analysis/v1", "music_id": "m1", "duration": 2,
                 "beats": [0.1, 0.5], "accents": [0.4],
                 "sections": [{"type": "intro", "in": 0, "out": 2}]}
        self.assertIsNone(validate_music_analysis(valid, "m1"))
        for invalid in ({**valid, "schema": "wrong"}, {**valid, "music_id": "other"},
                        {**valid, "beats": [0.5, 0.1]}, {**valid, "accents": [float("inf")]},
                        {**valid, "sections": [{"type": "intro", "in": 1, "out": 0.5}]}):
            with self.assertRaises(ValueError):
                validate_music_analysis(invalid, "m1")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg unavailable")
    def test_proposal_renders_storyboard_looks_and_beat_map(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            part = root / "part.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=30:d=2",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(part)], check=True)
            out = root / "proposal"
            render_proposal(library_for(part), edit_for(), load_looks(SCRIPTS.parent / "looks.json"), out,
                            music_analysis={"schema": "aerial-music-analysis/v1", "music_id": "m1", "duration": 2,
                                            "beats": [0.2], "accents": [0.5],
                                            "sections": [{"type": "intro", "in": 0, "out": 1}]})
            self.assertTrue((out / "storyboard.jpg").is_file())
            look_paths = [out / "looks" / f"{look}.jpg" for look in ("natural", "warm-gold", "teal-orange")]
            self.assertTrue(all(path.is_file() for path in look_paths))
            look_sizes = []
            for path in look_paths:
                with Image.open(path) as image:
                    look_sizes.append(image.size)
            with Image.open(out / "storyboard.jpg") as storyboard:
                self.assertEqual(set(look_sizes), {storyboard.size})
            self.assertTrue((out / "beat-map.jpg").is_file())

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg unavailable")
    def test_proposal_adds_stable_selected_custom_lut_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            part, cube = root / "part.mp4", root / "custom.cube"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=30:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(part)], check=True)
            cube.write_text("TITLE custom\nLUT_3D_SIZE 2\n0 0 0\n0 0 1\n0 1 0\n0 1 1\n1 0 0\n1 0 1\n1 1 0\n1 1 1\n", encoding="utf-8")
            edit = edit_for()
            edit["look_id"] = str(cube)
            out = root / "proposal"
            render_proposal(library_for(part), edit, load_looks(SCRIPTS.parent / "looks.json"), out)
            self.assertTrue((out / "looks" / "approved-lut.jpg").is_file())

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg unavailable")
    def test_real_preview_writes_outputs_without_source_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            part, second, music = root / "part.mp4", root / "second.mp4", root / "music.wav"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "color=c=red:s=160x90:r=30:d=1",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(part)], check=True)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "color=c=green:s=160x90:r=30:d=1",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(second)], check=True)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                            str(music)], check=True)
            source = "D:/not-to-be-exposed/raw.mp4"
            edit_path = root / "edit.json"
            library = library_for(part, source)
            library["parts"].append({**library["parts"][0], "id": "p2", "file": str(second)})
            edit = edit_for()
            edit["timeline"][0]["source_out"] = 1
            edit["timeline"].append({"part_id": "p2", "role": "build", "source_in": 0,
                                     "source_out": 1, "cut_at": .75, "transition": "fade", "beat_kind": "beat"})
            edit["target_sec"] = 1.75
            edit_path.write_text(json.dumps(edit), encoding="utf-8")
            result = render_rhythm_preview(library, edit,
                                           {"natural": {"vf": "null"}}, root, music,
                                           edit_path, ffmpeg="ffmpeg")
            self.assertTrue(result.is_file())
            sidecar = (root / "rhythm-preview.json").read_text(encoding="utf-8")
            self.assertNotIn(source, sidecar)
            metadata = json.loads(sidecar)
            self.assertEqual(metadata["part_ids"], ["p1", "p2"])
            self.assertEqual(metadata["output_duration"], 1.75)
            self.assertTrue(metadata["music_sha256"])
            probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,pix_fmt,width,height,r_frame_rate,duration", "-of", "json", str(result)], text=True))
            self.assertAlmostEqual(float(probe["format"]["duration"]), 1.75, delta=.12)
            video = next(item for item in probe["streams"] if item["codec_name"] == "h264")
            audio = next(item for item in probe["streams"] if item["codec_name"] == "aac")
            self.assertEqual((video["width"], video["height"], video["pix_fmt"], video["r_frame_rate"]), (1280, 720, "yuv420p", "30/1"))
            self.assertEqual(audio["codec_name"], "aac")
            self.assertAlmostEqual(float(audio["duration"]), 1.75, delta=.12)


if __name__ == "__main__":
    unittest.main()
