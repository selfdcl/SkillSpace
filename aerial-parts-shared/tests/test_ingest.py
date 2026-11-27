"""Black-box tests for source-preserving ingest helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import probe
import analyze_changes
import cut_part
import extract_frames


class IngestSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise unittest.SkipTest("ffmpeg and ffprobe are required")

    def _make_source(self, root: Path, name: str) -> Path:
        source = root / name
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=30:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
            ],
            check=True,
        )
        return source

    def _reject_source_resolve(self, source: Path):
        original_resolve = Path.resolve

        def mapped_drive_resolve(path: Path, strict: bool = False) -> Path:
            if path == source:
                raise OSError(1005, "unsupported mapped drive")
            return original_resolve(path, strict=strict)

        return mock.patch.object(Path, "resolve", mapped_drive_resolve)

    def test_probe_accepts_one_external_file_without_copying_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir = root / "external"
            job_dir = root / "job"
            source_dir.mkdir()
            source = source_dir / "DJI_0001.MP4"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=1:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
                ],
                check=True,
            )

            inventory = job_dir / "inventory.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "probe.py"),
                    "--input",
                    str(source),
                    "--output",
                    str(inventory),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(inventory.read_text(encoding="utf-8"))
            self.assertEqual(data["source_dir"], str(source_dir.resolve()))
            self.assertEqual(data["video_count"], 1)
            self.assertEqual(data["videos"][0]["path"], str(source.resolve()))
            self.assertEqual(sorted(path.name for path in job_dir.iterdir()), ["inventory.json"])

    def test_probe_works_when_mapped_drive_does_not_support_resolve(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "DJI_0002.MP4"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=1:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
                ],
                check=True,
            )
            inventory = root / "job" / "inventory.json"

            with mock.patch.object(Path, "resolve", side_effect=OSError(1005, "unsupported mapped drive")):
                with mock.patch.object(
                    sys,
                    "argv",
                    ["probe.py", "--input", str(source), "--output", str(inventory)],
                ):
                    try:
                        probe.main()
                    except OSError as exc:
                        self.fail(f"probe crashed on an accessible mapped-drive path: {exc}")

            data = json.loads(inventory.read_text(encoding="utf-8"))
            self.assertEqual(data["video_count"], 1)
            self.assertEqual(data["videos"][0]["path"], str(source.absolute()))

    def test_extract_frames_accepts_mapped_drive_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._make_source(root, "DJI_0003.MP4")
            out_dir = root / "frames"
            with self._reject_source_resolve(source):
                with mock.patch.object(
                    sys,
                    "argv",
                    ["extract_frames.py", "--input", str(source), "--out-dir", str(out_dir), "--interval", "1", "--width", "64"],
                ):
                    try:
                        extract_frames.main()
                    except OSError as exc:
                        self.fail(f"frame extraction crashed on an accessible mapped-drive path: {exc}")
            self.assertTrue((out_dir / "DJI_0003_frames.json").is_file())

    def test_analyze_changes_accepts_mapped_drive_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._make_source(root, "DJI_0004.MP4")
            output = root / "changes.json"
            with self._reject_source_resolve(source):
                with mock.patch.object(
                    sys,
                    "argv",
                    ["analyze_changes.py", "--input", str(source), "--output", str(output), "--interval", "1", "--width", "64"],
                ):
                    try:
                        analyze_changes.main()
                    except OSError as exc:
                        self.fail(f"change analysis crashed on an accessible mapped-drive path: {exc}")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["src"], str(source.absolute()))

    def test_cut_part_accepts_mapped_drive_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._make_source(root, "DJI_0005.MP4")
            output = root / "parts" / "sel_0005_001.mp4"
            with self._reject_source_resolve(source):
                with mock.patch.object(
                    sys,
                    "argv",
                    ["cut_part.py", "--src", str(source), "--start", "0", "--end", "1", "--out", str(output), "--mode", "encode"],
                ):
                    try:
                        cut_part.main()
                    except OSError as exc:
                        self.fail(f"cutting crashed on an accessible mapped-drive path: {exc}")
            self.assertGreater(output.stat().st_size, 0)

    def test_automatic_candidates_need_no_extracted_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = Path(r"Z:\footage\DJI_0099.MP4")
            inventory = root / "inventory.json"
            window_plan = root / "window-plan.json"
            output = root / "candidates.json"
            inventory.write_text(
                json.dumps(
                    {
                        "source_dir": str(source.parent),
                        "video_count": 1,
                        "videos": [
                            {
                                "path": str(source),
                                "duration": 20.0,
                                "width": 3840,
                                "height": 2160,
                                "fps": "30000/1001",
                                "audio": False,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            window_plan.write_text(
                json.dumps(
                    {
                        "schema": "aerial-window-plan/v1",
                        "src": str(source),
                        "groups": [
                            {
                                "motion_group": "motion_01",
                                "windows": [
                                    {"in": 0.0, "out": 5.0, "phase": "起势", "motion_group": "motion_01"},
                                    {"in": 7.0, "out": 12.0, "phase": "收束", "motion_group": "motion_01"},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "candidates_from_windows.py"),
                    "--inventory",
                    str(inventory),
                    "--window-plan",
                    str(window_plan),
                    "--output",
                    str(output),
                    "--id-prefix",
                    "sel_0099",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["selection_mode"], "automatic")
            self.assertEqual([item["id"] for item in data["keep"]], ["sel_0099_001", "sel_0099_002"])
            self.assertEqual(data["keep"][0]["shot"], "未定")
            self.assertEqual(data["keep"][0]["light"], "未定")
            self.assertEqual(data["keep"][0]["quality"], "可用")
            self.assertEqual(data["keep"][0]["note"], "自动窗口，未人工判片")
            self.assertFalse((root / "frames").exists())

    def test_cut_candidates_skips_marginal_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._make_source(root, "DJI_0100.MP4")
            candidates = root / "candidates.json"
            candidates.write_text(
                json.dumps(
                    {
                        "keep": [
                            {
                                "id": "sel_0100_001",
                                "src": str(source),
                                "in": 0.0,
                                "out": 0.8,
                                "quality": "可用",
                            },
                            {
                                "id": "sel_0100_002",
                                "src": str(source),
                                "in": 0.8,
                                "out": 1.6,
                                "quality": "勉强",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out_dir = root / "parts"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "cut_candidates.py"),
                    "--candidates",
                    str(candidates),
                    "--out-dir",
                    str(out_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out_dir / "sel_0100_001.mp4").is_file())
            self.assertFalse((out_dir / "sel_0100_002.mp4").exists())
            self.assertIn("skipped 1 marginal", result.stdout)

    def test_cut_candidates_includes_marginal_only_when_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._make_source(root, "DJI_0101.MP4")
            candidates = root / "candidates.json"
            candidates.write_text(
                json.dumps(
                    {
                        "keep": [
                            {
                                "id": "sel_0101_001",
                                "src": str(source),
                                "in": 0.0,
                                "out": 0.8,
                                "quality": "可用",
                            },
                            {
                                "id": "sel_0101_002",
                                "src": str(source),
                                "in": 0.8,
                                "out": 1.6,
                                "quality": "勉强",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out_dir = root / "parts"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "cut_candidates.py"),
                    "--candidates",
                    str(candidates),
                    "--out-dir",
                    str(out_dir),
                    "--include-marginal",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out_dir / "sel_0101_001.mp4").is_file())
            self.assertTrue((out_dir / "sel_0101_002.mp4").is_file())


if __name__ == "__main__":
    unittest.main()
