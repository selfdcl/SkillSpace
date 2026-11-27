---
name: aerial-video-director
description: Use when a validated drone-shot library must become a reviewable aerial video proposal before editing, including shot selection, local music choices, storyboard, look comparison, and a rhythm preview.
---

# Aerial video direction

Turn a validated shot-parts library into a reviewable proposal, not a final edit. Accept only aerial-parts/v1 library.json; write artifacts under the job proposal directory. Source footage stays read-only.

## Boundaries

- Select, extract frames, and render only with library.json parts[].id and parts[].file. 不得读取 parts[].src; do not scan original-footage directories or invent part IDs.
- Run `validate_pipeline.py --library <job>\library.json --check-files` first. Report its errors and stop if it fails. This is the consumer check: it verifies the aerial-parts/v1 metadata and extracted `parts[].file` assets without reading source footage.
- If required framing, subject, move, usable duration, or authorized local music is missing, record the gap in edit.json missing and explain it. Never fill it with an invented clip or music.
- Music priority is a user-specified local file, the user licensed music-library.json, then an explicit missing-music request. Show at most three candidates per proposal; never fetch unlicensed internet music.
- Cut priority is narrative logic > complete musical phrases > accents/downbeats > ordinary beats. Let shots breathe through phrases and place reveals on section starts or accents; do not cut chaotically on every beat, truncate important action, or retime by default.
- Generating a proposal is not approval. Before the user gives 用户明确确认, do not create or alter approval.json; show the proposal and stop.

## Checklist

~~~
- [ ] 1. Validate library.json; stop on failure
- [ ] 2. Turn the user request into brief.json
- [ ] 3. Select only from library.json and write aerial-edit/v2
- [ ] 4. Offer no more than three candidates from local licensed music
- [ ] 5. Analyze music and align cuts to phrases, accents, and visual events
- [ ] 6. Generate video-script.md, storyboard.jpg, three built-in looks (and `looks/approved-lut.jpg` for a selected `.cube`), and rhythm-preview.mp4
- [ ] 7. Show the proposal and stop, waiting for 用户明确确认
- [ ] 8. After confirmation, write approval.json bound to the current edit.json
~~~

## Validate, brief, and select

Run the example from the SkillSpace repository root. Use the parent of this skill's actual directory to locate the repository.

~~~
python aerial-parts-shared/scripts/validate_pipeline.py --library <job>\library.json --check-files
~~~

Write proposal/brief.json from the request. Ask about missing direction-changing details (target, platform/aspect, pace, color, title/caption/voiceover, or music rights); record reversible defaults in both the brief and script.

Use only library labels, notes, and representative frames from parts[].file. Every timeline part_id must exist, and its source_in/out must fit that part duration. Write proposal/edit.json as aerial-edit/v2; put unsatisfied requirements in missing.

## Music and review artifacts

Check the readability and license note of a specified local track. Otherwise rank the local licensed library by theme, pace, vocals, and commercial need, show at most three, then choose one for this proposal. Analyze the selected track and arrange cuts around phrases and visual events.

Generate video-script.md, storyboard.jpg, looks/natural.jpg, looks/warm-gold.jpg, looks/teal-orange.jpg, beat-map.jpg, rhythm-preview.mp4, and their supporting JSON. If the selected look is a readable local `.cube`, also generate and show `looks/approved-lut.jpg`. Read references.md when writing fields, running commands, or recovering a failed artifact.

## Confirmation gate

Show the script, chosen music and up to three candidates, three built-in looks, rhythm preview, and missing gaps. Include `looks/approved-lut.jpg` when a custom LUT is selected. Then stop.

Only after 用户明确确认 of the current script, music, and look may you write proposal/approval.json. It must have status approved and exact current edit_sha256, look_id, look_sha256, music_id, and music_sha256 bindings. Any edit revision or selected music/look byte change invalidates approval: retain the old proposal/preview, create a revision, and wait for confirmation again.
