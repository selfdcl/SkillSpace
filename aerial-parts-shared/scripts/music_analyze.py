"""Local beat, accent, and energy analysis for an audio track."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from pipeline_common import sha256_file, write_json_object

SAMPLE_RATE = 22050
librosa = None


def _number(value: float) -> float:
    value = float(value)
    return round(value, 3) if math.isfinite(value) else 0.0


def _times(values: np.ndarray) -> list[float]:
    return [_number(value) for value in np.asarray(values).reshape(-1)]


def _get_librosa():
    global librosa
    if librosa is None:
        import librosa as librosa_module
        librosa = librosa_module
    return librosa


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load a local audio file as mono 22050 Hz PCM samples."""
    audio_library = _get_librosa()
    audio, sample_rate = audio_library.load(Path(path), sr=SAMPLE_RATE, mono=True)
    return np.asarray(audio), int(sample_rate)


def select_accents(strengths: np.ndarray, times: np.ndarray) -> list[float]:
    """Keep strong onset events at least a quarter second apart."""
    strengths = np.asarray(strengths, dtype=float).reshape(-1)
    times = np.asarray(times, dtype=float).reshape(-1)
    if not len(strengths) or not len(times):
        return []
    finite_strengths = strengths[np.isfinite(strengths)]
    if not len(finite_strengths):
        return []
    threshold = float(np.percentile(finite_strengths, 75))
    accents: list[float] = []
    last_timestamp: float | None = None
    for strength, timestamp in zip(strengths, times):
        if math.isfinite(float(strength)) and math.isfinite(float(timestamp)) and strength >= threshold:
            original_timestamp = float(timestamp)
            if last_timestamp is None or original_timestamp - last_timestamp >= 0.25:
                accents.append(_number(original_timestamp))
                last_timestamp = original_timestamp
    return accents


def build_sections(duration: float, candidates: list[float]) -> list[dict]:
    """Build the four ordered narrative sections from energy-change times."""
    duration = max(0.0, float(duration))
    usable = sorted({max(0.0, min(duration, float(item))) for item in candidates
                     if math.isfinite(float(item))})
    targets = [0.0, duration * 0.2, duration * 0.6, duration * 0.85]
    boundaries: list[float] = []
    for index, target in enumerate(targets):
        minimum = boundaries[-1] if boundaries else 0.0
        choices = [candidate for candidate in usable if candidate >= minimum]
        choice = min(choices, key=lambda item: (abs(item - target), item)) if choices else target
        boundaries.append(max(minimum, min(duration, choice)))
    return [
        {"type": kind, "in": _number(start), "out": _number(end)}
        for kind, start, end in zip(
            ["intro", "build", "climax", "outro"], boundaries,
            boundaries[1:] + [duration],
        )
    ]


def analyze_music(path: Path, music_id: str) -> dict:
    """Analyze one readable local audio file without network access."""
    path = Path(path)
    audio_library = _get_librosa()
    audio, sample_rate = load_audio(path)
    duration = float(audio_library.get_duration(y=audio, sr=sample_rate))
    onset_envelope = audio_library.onset.onset_strength(y=audio, sr=sample_rate)
    tempo, beat_frames = audio_library.beat.beat_track(onset_envelope=onset_envelope, sr=sample_rate)
    beat_frames = np.asarray(beat_frames, dtype=int)
    beat_times = audio_library.frames_to_time(beat_frames, sr=sample_rate)
    onset_frames = audio_library.onset.onset_detect(onset_envelope=onset_envelope, units="frames")
    onset_times = audio_library.frames_to_time(onset_frames, sr=sample_rate)
    onset_strengths = onset_envelope[np.asarray(onset_frames, dtype=int)] if len(onset_frames) else np.array([])
    rms = audio_library.feature.rms(y=audio)[0]
    rms_frames = np.arange(len(rms))
    rms_times = audio_library.frames_to_time(rms_frames, sr=sample_rate)
    energy_candidates = rms_times[1:][np.abs(np.diff(rms)) > 0] if len(rms) > 1 else np.array([])
    beat_energy = [
        {"time": _number(time), "rms": _number(rms[min(int(frame), len(rms) - 1)])}
        for time, frame in zip(beat_times, beat_frames)
    ] if len(rms) else []
    tempo_value = float(np.asarray(tempo).reshape(-1)[0]) if np.asarray(tempo).size else 0.0
    return {
        "schema": "aerial-music-analysis/v1",
        "music_id": music_id,
        "source_sha256": sha256_file(path),
        "duration": _number(duration),
        "bpm": _number(tempo_value),
        "beats": _times(beat_times),
        "accents": select_accents(onset_strengths, onset_times),
        "energy": beat_energy,
        "sections": build_sections(duration, _times(energy_candidates)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one local music file.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--music-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    write_json_object(args.output, analyze_music(args.input, args.music_id))


if __name__ == "__main__":
    main()
