import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import soundfile as sf

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from music_analyze import analyze_music, build_sections, load_audio, select_accents
from music_search import search_music, validate_music_library


class MusicTest(unittest.TestCase):
    def test_music_library_fails_closed_for_schema_license_duplicate_and_nonfinite_bpm(self):
        valid = {"schema": "aerial-music-library/v1", "tracks": [{"id": "one", "file": "one.wav", "license": "CC0"}]}
        self.assertIsNone(validate_music_library(valid))
        for invalid in (
            {**valid, "schema": "wrong"},
            {"schema": "aerial-music-library/v1", "tracks": [{"id": "one", "file": "one.wav", "license": ""}]},
            {"schema": "aerial-music-library/v1", "tracks": [valid["tracks"][0], valid["tracks"][0]]},
            {"schema": "aerial-music-library/v1", "tracks": [{"id": "one", "file": "one.wav", "license": "CC0", "bpm": float("nan")} ]},
        ):
            with self.assertRaises(ValueError):
                validate_music_library(invalid)

    def test_search_rejects_invalid_library_before_ranking(self):
        with self.assertRaisesRegex(ValueError, "license"):
            search_music({"schema": "aerial-music-library/v1", "tracks": [{"id": "one", "file": "one.wav", "license": ""}]}, {})
    def test_matching_tracks_rank_by_score_then_id(self):
        library = {"schema": "aerial-music-library/v1", "tracks": [
            {"id": "zulu", "file": "zulu.wav", "moods": ["calm"],
             "genres": ["ambient"], "bpm": 80, "vocal": False,
             "commercial": True, "license": "CC0"},
            {"id": "alpha", "file": "alpha.wav", "moods": ["calm"],
             "genres": ["ambient"], "bpm": 80, "vocal": False,
             "commercial": True, "license": "CC0"},
            {"id": "other", "file": "other.wav", "moods": ["bright"],
             "genres": ["rock"], "bpm": 150, "vocal": False,
             "commercial": True, "license": "CC0"},
        ]}
        profile = {"moods": ["calm"], "genres": ["ambient"],
                   "bpm_min": 70, "bpm_max": 90}

        self.assertEqual([item["id"] for item in search_music(library, profile)],
                         ["alpha", "zulu", "other"])
        self.assertEqual(search_music(library, profile)[0]["score"], 10.0)

    def test_commercial_and_explicit_vocal_filters_are_hard_filters(self):
        library = {"schema": "aerial-music-library/v1", "tracks": [
            {"id": "licensed-instrumental", "file": "a.wav", "commercial": True,
             "vocal": False, "license": "CC0"},
            {"id": "unlicensed-instrumental", "file": "b.wav", "commercial": False,
             "vocal": False, "license": "CC0"},
            {"id": "licensed-vocal", "file": "c.wav", "commercial": True,
             "vocal": True, "license": "CC0"},
        ]}

        self.assertEqual(
            [item["id"] for item in search_music(library, {
                "commercial_required": True, "vocal": False
            })],
            ["licensed-instrumental"],
        )

    def test_bpm_distance_reduces_score_by_one_per_ten_bpm(self):
        library = {"schema": "aerial-music-library/v1", "tracks": [
            {"id": "inside", "file": "inside.wav", "bpm": 90, "license": "CC0"},
            {"id": "near", "file": "near.wav", "bpm": 110, "license": "CC0"},
            {"id": "far", "file": "far.wav", "bpm": 130, "license": "CC0"},
        ]}
        matches = search_music(library, {"bpm_min": 80, "bpm_max": 100})

        self.assertEqual([(item["id"], item["score"]) for item in matches],
                         [("inside", 4.0), ("near", -1.0), ("far", -3.0)])

    def test_sections_are_ordered_and_end_at_duration(self):
        sections = build_sections(30.0, [0.0, 5.7, 17.1, 25.7])

        self.assertEqual([section["type"] for section in sections],
                         ["intro", "build", "climax", "outro"])
        self.assertEqual([section["in"] for section in sections], [0.0, 5.7, 17.1, 25.7])
        self.assertEqual([section["out"] for section in sections], [5.7, 17.1, 25.7, 30.0])

    def test_accents_use_percentile_and_minimum_spacing(self):
        accents = select_accents(
            np.array([1.0, 5.0, 5.0, 5.0]), np.array([0.0, 0.1, 0.3, 0.6])
        )

        self.assertEqual(accents, [0.1, 0.6])

    def test_accents_compare_original_timestamps_before_rounding(self):
        accents = select_accents(
            np.array([1.0, 5.0, 5.0, 5.0]),
            np.array([0.0, 0.2498, 0.2501, 0.5002]),
        )

        self.assertEqual(accents, [0.25, 0.5])

    def test_accents_ignore_nonfinite_strengths_when_computing_percentile(self):
        accents = select_accents(
            np.array([np.nan, 1.0, 4.0, 5.0]),
            np.array([0.0, 0.1, 0.4, 0.8]),
        )

        self.assertEqual(accents, [0.8])

    def test_nonfinite_bpm_is_rejected_by_the_library_boundary(self):
        library = {"schema": "aerial-music-library/v1", "tracks": [
            {"id": "infinite", "file": "a.wav", "bpm": float("inf"), "license": "CC0"},
            {"id": "nan", "file": "b.wav", "bpm": float("nan"), "license": "CC0"},
            {"id": "normal", "file": "c.wav", "bpm": 90, "license": "CC0"},
        ]}
        with self.assertRaisesRegex(ValueError, "bpm"):
            search_music(library, {"bpm_min": float("nan"), "bpm_max": 100})

    def test_search_music_is_independent_of_current_working_directory(self):
        library = {"schema": "aerial-music-library/v1", "tracks": [
            {"id": "relative", "file": "audio/track.wav", "license": "CC0"},
        ]}
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                matches = search_music(library, {})
            finally:
                os.chdir(original)

        self.assertEqual(matches[0]["file"], "audio/track.wav")

    def test_search_cli_resolves_relative_files_from_library_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library_path = root / "library.json"
            profile_path = root / "profile.json"
            output_path = root / "output.json"
            audio_path = root / "track.wav"
            sf.write(audio_path, np.zeros(100, dtype=np.float32), 22050)
            library_path.write_text(json.dumps({"schema": "aerial-music-library/v1", "tracks": [{
                "id": "relative", "file": "track.wav", "license": "CC0",
                "moods": ["calm"], "genres": ["ambient"], "commercial": True,
            }]}), encoding="utf-8")
            profile_path.write_text(json.dumps({"moods": ["calm"]}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "music_search.py"), "--library", str(library_path),
                 "--profile", str(profile_path), "--output", str(output_path)],
                cwd=str(root.parent), shell=False, capture_output=True, text=True,
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["tracks"][0]["file"], str(audio_path.resolve()))

    def test_load_audio_uses_real_librosa_for_mono_22050_output(self):
        stereo = np.column_stack((np.ones(4410, dtype=np.float32), -np.ones(4410, dtype=np.float32)))
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "stereo.wav"
            sf.write(audio_path, stereo, 44100)
            audio, sample_rate = load_audio(audio_path)

        self.assertEqual(sample_rate, 22050)
        self.assertEqual(audio.ndim, 1)

    @unittest.skipUnless(
        os.environ.get("RUN_SLOW_LIBROSA_TESTS") == "1",
        "set RUN_SLOW_LIBROSA_TESTS=1 to run real librosa beat analysis",
    )
    def test_slow_real_librosa_analysis_is_finite_and_ordered(self):
        sample_rate = 22050
        samples = np.zeros(sample_rate * 2, dtype=np.float32)
        samples[::2205] = 0.8
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "click-track.wav"
            sf.write(audio_path, samples, sample_rate)
            analysis = analyze_music(audio_path, "click-track")
            encoded = json.dumps(analysis, allow_nan=False)

        self.assertEqual(analysis["schema"], "aerial-music-analysis/v1")
        self.assertTrue(math.isfinite(analysis["bpm"]))
        self.assertTrue(all(math.isfinite(timestamp) for timestamp in analysis["beats"]))
        self.assertTrue(all(math.isfinite(timestamp) for timestamp in analysis["accents"]))
        self.assertTrue(all(math.isfinite(item["time"]) and math.isfinite(item["rms"])
                            for item in analysis["energy"]))
        self.assertEqual([item["type"] for item in analysis["sections"]],
                         ["intro", "build", "climax", "outro"])
        self.assertEqual(analysis["sections"][-1]["out"], analysis["duration"])
        self.assertIsInstance(encoded, str)

    def test_analysis_serializes_without_nan(self):
        sample_rate = 22050
        samples = np.zeros(sample_rate, dtype=np.float32)
        samples[::2205] = 0.8
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "clicks.wav"
            sf.write(audio_path, samples, sample_rate)
            library_stub = SimpleNamespace(
                load=lambda *_args, **_kwargs: (samples, sample_rate),
                get_duration=lambda **_kwargs: 1.0,
                frames_to_time=lambda frames, **_kwargs: np.asarray(frames, dtype=float) / 10,
                onset=SimpleNamespace(
                    onset_strength=lambda **_kwargs: np.array([0.0, 2.0, 4.0]),
                    onset_detect=lambda **_kwargs: np.array([1, 2]),
                ),
                beat=SimpleNamespace(
                    beat_track=lambda **_kwargs: (120.0, np.array([0, 2])),
                ),
                feature=SimpleNamespace(rms=lambda **_kwargs: np.array([[0.0, np.nan, 0.5]])),
            )
            with patch("music_analyze.librosa", library_stub):
                analysis = analyze_music(audio_path, "clicks")
            encoded = json.dumps(analysis, allow_nan=False)

        self.assertEqual(analysis["schema"], "aerial-music-analysis/v1")
        self.assertEqual(analysis["music_id"], "clicks")
        self.assertEqual(len(analysis["source_sha256"]), 64)
        self.assertIsInstance(encoded, str)
        self.assertTrue(all(
            math.isfinite(value)
            for values in (analysis["beats"], analysis["accents"])
            for value in values
        ))
        self.assertTrue(all(math.isfinite(item["rms"]) for item in analysis["energy"]))


if __name__ == "__main__":
    unittest.main()
