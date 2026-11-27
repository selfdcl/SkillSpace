"""Black-box workflow coverage for an approved aerial edit."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "aerial-parts-shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pipeline_common import sha256_file


class AerialEditorE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise unittest.SkipTest("ffmpeg and ffprobe are required for aerial editor E2E")

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(args, check=check, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def _script(self, name: str) -> str:
        return str(SCRIPTS / name)

    def _probe(self, path: Path) -> dict:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return json.loads(result.stdout)

    def _write_inputs(self, root: Path, *, animated: bool = False) -> tuple[Path, Path, Path, Path, Path, Path]:
        media = root / "media"
        proposal = root / "proposal"
        media.mkdir()
        clip, music = media / "motion.mp4", media / "music.wav"
        self._run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip))
        self._run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=10", "-c:a", "pcm_s16le", str(music))
        library = {"schema": "aerial-parts/v1", "created": "2026-08-23T00:00:00Z", "source_dir": "not-used", "parts_dir": str(media), "parts": [{"id": "part-1", "in": 0.0, "out": 6.0, "file": str(clip), "dur": 6.0, "shot": "横移", "subject": "test pattern", "light": "晴", "move": "left to right", "quality": "可用", "note": "generated motion"}]}
        brief = {"schema": "aerial-brief/v1", "theme": "E2E", "target_sec": 6, "platform": "test", "aspect": "16:9", "pace": "normal", "look_request": "warm", "titles": animated, "subtitles": False, "voiceover": False, "music": {"source": "local", "vocal": False, "commercial_required": False}}
        edit = {"schema": "aerial-edit/v2", "theme": "E2E", "target_sec": 6, "aspect": "16:9", "look_id": "warm-gold", "music_id": "tone", "timeline": [{"part_id": "part-1", "role": "opening", "source_in": 0.0, "source_out": 6.0, "cut_at": 0.0, "transition": "cut", "beat_kind": "downbeat"}], "titles": ([{"text": "E2E", "start_sec": 0.5, "end_sec": 2.0, "animated": True}] if animated else []), "captions": [], "graphics": [], "missing": []}
        library_path, brief_path, edit_path = root / "library.json", proposal / "brief.json", proposal / "edit.json"
        proposal.mkdir()
        for path, value in ((library_path, library), (brief_path, brief), (edit_path, edit)):
            path.write_text(json.dumps(value), encoding="utf-8")
        looks = json.loads((ROOT / "aerial-parts-shared" / "looks.json").read_text(encoding="utf-8"))
        look = next(item for item in looks["looks"] if item["id"] == "warm-gold")
        look_hash = hashlib.sha256(json.dumps(look, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        approval = {"schema": "aerial-approval/v1", "status": "approved", "edit_sha256": sha256_file(edit_path), "look_id": "warm-gold", "look_sha256": look_hash, "music_id": "tone", "music_sha256": sha256_file(music), "approved_at": "2026-08-23T00:00:00Z"}
        approval_path = proposal / "approval.json"
        approval_path.write_text(json.dumps(approval), encoding="utf-8")
        return library_path, brief_path, edit_path, approval_path, music, proposal

    def _exercise(self, *, animated: bool = False) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library, brief, edit, approval, music, proposal = self._write_inputs(root, animated=animated)
            looks = ROOT / "aerial-parts-shared" / "looks.json"
            self._run(sys.executable, self._script("render_proposal.py"), "--library", str(library), "--edit", str(edit), "--looks", str(looks), "--out-dir", str(proposal))
            self._run(sys.executable, self._script("render_rhythm_preview.py"), "--library", str(library), "--edit", str(edit), "--looks", str(looks), "--out-dir", str(proposal), "--music", str(music))
            output, work = root / "output", root / "work"
            self._run(sys.executable, self._script("render_ffmpeg.py"), "--library", str(library), "--brief", str(brief), "--edit", str(edit), "--approval", str(approval), "--looks", str(looks), "--music", str(music), "--work-dir", str(work), "--output-dir", str(output))
            preview = output / "preview.mp4"
            rejected = self._run(sys.executable, self._script("publish_delivery.py"), "--preview", str(preview), "--report", str(output / "edit-report.json"), "--output-dir", str(output), "--edit", str(edit), check=False)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("user confirmation required", rejected.stderr)
            self._run(sys.executable, self._script("publish_delivery.py"), "--preview", str(preview), "--report", str(output / "edit-report.json"), "--output-dir", str(output), "--user-confirmed", "--edit", str(edit))
            final = output / "final.mp4"
            for artifact in (proposal / "storyboard.jpg", proposal / "beat-map.jpg", proposal / "looks" / "natural.jpg", proposal / "looks" / "warm-gold.jpg", proposal / "looks" / "teal-orange.jpg", proposal / "rhythm-preview.mp4", work / "base.mp4", preview, final):
                self.assertGreater(artifact.stat().st_size, 0, artifact)
            report = json.loads((output / "edit-report.json").read_text())
            self.assertEqual(report["edit_sha256"], sha256_file(edit))
            self.assertEqual(report["music_sha256"], sha256_file(music))
            self.assertEqual(report["preview_sha256"], sha256_file(preview))
            self.assertEqual(report["renderer"], "ffmpeg+remotion" if animated else "ffmpeg")
            streams = self._probe(preview)["streams"]
            video = next(stream for stream in streams if stream["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (1920, 1080))
            self.assertTrue(any(stream["codec_type"] == "audio" for stream in streams))

    def test_approved_ffmpeg_edit_can_be_previewed_then_confirmed(self):
        self._exercise()

    def test_animated_title_uses_remotion_only_with_an_explicit_license_key(self):
        if not os.environ.get("REMOTION_LICENSE_KEY", "").strip():
            self.skipTest("REMOTION_LICENSE_KEY is not explicitly configured; free-license is never set by this test")
        if shutil.which("npx") is None or not (ROOT / "aerial-parts-shared" / "remotion" / "node_modules").is_dir():
            self.skipTest("installed Remotion CLI dependencies are unavailable")
        self._exercise(animated=True)


if __name__ == "__main__":
    unittest.main()
