# Editor commands and recovery

Read this reference while rendering, recovering a failed run, or publishing. `$job` is the job directory and `$py` is `./aerial-parts-shared/scripts`.

## Render and publish

Run these examples from the SkillSpace repository root. Replace the example job and music paths with your own.

```powershell
$py = './aerial-parts-shared/scripts'
$job = 'D:\edit-job'
$music = 'D:\licensed\track.wav'
python "$py\validate_pipeline.py" --library "$job\library.json" --check-files
python "$py\validate_pipeline.py" --library "$job\library.json" --brief "$job\proposal\brief.json" --edit "$job\proposal\edit.json" --approval "$job\proposal\approval.json" --check-files
python "$py\render_ffmpeg.py" --library "$job\library.json" --brief "$job\proposal\brief.json" --edit "$job\proposal\edit.json" --approval "$job\proposal\approval.json" --looks './aerial-parts-shared/looks.json' --music $music --work-dir "$job\work" --output-dir "$job\output"
# Show output\preview.mp4 and stop. Run only after the user explicitly confirms this preview as the final video.
python "$py\publish_delivery.py" --preview "$job\output\preview.mp4" --report "$job\output\edit-report.json" --output-dir "$job\output" --user-confirmed --edit "$job\proposal\edit.json"
```

The validator confirms the proposal and the approval's edit binding. The renderer independently checks all approval bindings: `edit_sha256`, `music_sha256`, `look_sha256`, `music_id`, and `look_id`.

## Optional overlay and Jianying handoff

`captions`, `graphics`, or a title with `animated: true` requires Remotion. Set `REMOTION_LICENSE_KEY` in the caller environment before rendering; if it is absent, stop before creating overlay assets. Do not set `free-license` in automation. Use a Remotion license key only when the user's eligibility and license terms allow it; otherwise obtain a purchased key.

```powershell
python "$py\publish_delivery.py" --preview "$job\output\preview.mp4" --report "$job\output\edit-report.json" --output-dir "$job\output" --user-confirmed --jianying --library "$job\library.json" --edit "$job\proposal\edit.json" --music $music --storyboard "$job\proposal\storyboard.jpg" --handoff-dir "$job\handoff-jianying"
```

This copies usable assets and an edit list; it is not a native Jianying draft and does not create one. For a selected custom `.cube`, the handoff resolves it from `edit.look_id`, requires its SHA-256 to equal `edit-report.json.look_sha256`, and copies it into `lut/` automatically. Supplying `--cube` is optional only for that custom look and must resolve to the same file; it is rejected for built-in looks.

## Recovery

- Approval/hash failure or changed request: keep prior review output, create `proposal/revisions/<revision>/`, regenerate the affected proposal assets, and wait for a new confirmation.
- Missing part or music: record the actual missing requirement and stop; never replace it.
- FFmpeg/Remotion failure: retain `work/`, logs, and existing preview. Fix the input or renderer, then rerun only the failed render command.
- Publication failure: inspect the report/preview hashes, correct the mismatch, then request explicit final confirmation again. `publish_delivery.py` archives prior final artifacts rather than silently overwriting them.
