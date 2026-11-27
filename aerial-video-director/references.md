# Director contracts and recovery

Read this reference only while generating, checking, or recovering a proposal. In commands, <job> is the job directory and $py is ./aerial-parts-shared/scripts.

## Output layout and fields

~~~
<job>/proposal/
  brief.json  edit.json  video-script.md
  music-candidates.json  music-analysis.json
  storyboard.jpg  looks/{natural,warm-gold,teal-orange,approved-lut}.jpg  beat-map.jpg
  rhythm-preview.mp4  rhythm-preview.json
  approval.json                    # only after explicit user confirmation
~~~

brief.json (aerial-brief/v1) requires theme, target_sec, platform, aspect, pace, look_request, titles, subtitles, voiceover, and music.source/music.vocal/music.commercial_required.

edit.json (aerial-edit/v2) requires theme, target_sec, aspect, look_id, music_id, timeline, titles, captions, graphics, and missing. Each timeline item requires part_id, role, relative-file source_in/source_out, cut_at, transition (cut|fade|fade-black), and beat_kind (none|beat|downbeat|accent). The actual timeline duration must be within 0.5 seconds of both edit.target_sec and brief.target_sec; overlay starts must be non-negative and overlay ends must not exceed that actual duration. Timed title/caption fields are text, start_sec, end_sec; graphic fields are file, start_sec, end_sec, position, scale, opacity. missing is an array of real unmet needs.

music-library.json (aerial-music-library/v1) contains tracks. Every track has id, file, and license; it may have title, moods, genres, commercial, bpm, and vocal. music-candidates.json records selected, ranked (maximum three) readable local tracks.

music-analysis.json (aerial-music-analysis/v1) records music_id, source hash, duration, BPM, beats, accents, energy, and ordered sections. Arrange phrases/sections first and micro-adjust with accents.

approval.json (aerial-approval/v1) is created only after explicit confirmation. It contains schema, status: approved, edit_sha256, look_id, look_sha256, music_id, music_sha256, approved_at, and optional note. `music_sha256` hashes the exact selected local music file. For a built-in look, `look_sha256` is SHA-256 of that selected look object serialized as compact UTF-8 JSON with sorted keys; for an approved `.cube`, it is the LUT file SHA-256. All bindings must exactly match the current edit and selected assets.

Look IDs are natural (neutral baseline), warm-gold (warm sunset), and teal-orange (teal/orange contrast). Compare the same representative frames in each look. A readable selected local `.cube` additionally renders stable `looks/approved-lut.jpg`, and approval look_sha256 is the LUT byte hash.

## Commands

Run these examples from the SkillSpace repository root. Replace the example job and music paths with your own.

~~~powershell
$py = './aerial-parts-shared/scripts'
$job = 'D:\edit-job'
python "$py\validate_pipeline.py" --library "$job\library.json" --check-files
# Supply this JSON profile: moods, genres, bpm_min, bpm_max, vocal, commercial_required.
python "$py\music_search.py" --library "$job\music-library.json" --profile "$job\proposal\music-profile.json" --output "$job\proposal\music-candidates.json" --limit 3
python "$py\music_analyze.py" --input <selected-local-music-file> --music-id <music-id> --output "$job\proposal\music-analysis.json"
python "$py\validate_pipeline.py" --library "$job\library.json" --brief "$job\proposal\brief.json" --edit "$job\proposal\edit.json" --check-files
python "$py\render_proposal.py" --library "$job\library.json" --edit "$job\proposal\edit.json" --looks "./aerial-parts-shared/looks.json" --out-dir "$job\proposal" --music-analysis "$job\proposal\music-analysis.json"
python "$py\render_rhythm_preview.py" --library "$job\library.json" --edit "$job\proposal\edit.json" --looks "./aerial-parts-shared/looks.json" --music <selected-local-music-file> --out-dir "$job\proposal"
~~~

After confirmation only, hash and validate the new approval:

~~~powershell
$hash = (Get-FileHash "$job\proposal\edit.json" -Algorithm SHA256).Hash.ToLower()
$musicHash = (Get-FileHash '<selected-local-music-file>' -Algorithm SHA256).Hash.ToLower()
$lookHash = (Get-FileHash '<approved-look.cube>' -Algorithm SHA256).Hash.ToLower()
# For a built-in look, this exact canonical helper hashes sort_keys compact UTF-8 JSON:
$env:PYTHONUTF8 = '1'
$lookHash = python -c "import sys; from pathlib import Path; sys.path.insert(0, r'./aerial-parts-shared/scripts'); from render_ffmpeg import look_sha256; from render_proposal import load_looks; print(look_sha256('<look-id>', load_looks(Path(r'./aerial-parts-shared/looks.json'))))"
# Write approval.json with $hash, $musicHash, $lookHash and matching current look_id/music_id.
python "$py\validate_pipeline.py" --library "$job\library.json" --brief "$job\proposal\brief.json" --edit "$job\proposal\edit.json" --approval "$job\proposal\approval.json" --check-files
~~~

## Recovery

- Validation failure: repair the draft or input and rerun the consumer validator. It checks `parts[].file`, never `parts[].src`; `validate_library.py` remains an unchanged ingest-stage validator only.
- Storyboard/look failure: retain proposal/.frames and errors, confirm selected parts[].file paths are readable, then rerun render_proposal.py; do not overwrite an already reviewable proposal.
- Rhythm-preview failure: confirm readable selected music, matching music_id, a continuous timeline, and legal transitions; rerun only render_rhythm_preview.py.
- Changed request: make proposal/revisions/<revision>/, modify copied brief/edit, then rerender affected artifacts. Old approval cannot be reused.
