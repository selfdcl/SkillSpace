---
name: aerial-video-editor
description: Use when an approved aerial-video proposal needs a reviewable edit, a final confirmed MP4, or an optional Jianying import handoff.
---

# Aerial video editing

Produce an auditable review edit from a validated, approved proposal. FFmpeg is always the base renderer; Remotion is an overlay-only option for animated titles, captions, or graphics.

## Hard gates

- Consume only an `aerial-parts/v1` library that passes `validate_pipeline.py --library <job>\library.json --check-files`, and only an `aerial-edit/v2` proposal with a current approved `approval.json`. This consumer validation checks metadata and extracted parts only; the unchanged `validate_library.py` belongs to ingest.
- Verify the approval's exact `edit_sha256`, `music_sha256`, `look_sha256`, `music_id`, and `look_id` before rendering. A changed edit, music byte, or look byte is stale approval: preserve existing artifacts, make a revision, and return to proposal confirmation.
- Resolve shots only through `parts[].file`; never scan `source_dir` or use `parts[].src`. Do not substitute a missing clip or missing/unreadable music. Report the gap and stop.
- Show `preview.mp4` and stop. Never publish `final.mp4` until the user explicitly says 用户确认成片 for that preview.

## Checklist

- [ ] 1. 校验 library、brief、edit 和 approval 摘要
- [ ] 2. 用 FFmpeg 完成剪辑、调色、转场和音乐，生成 base.mp4
- [ ] 3. 有复杂包装层时用 Remotion 生成 preview.mp4，否则直接使用 base.mp4
- [ ] 4. 向用户展示 preview.mp4，停止等待确认
- [ ] 5. 用户明确确认成片后使用 --user-confirmed 发布 final.mp4
- [ ] 6. 用户需要时生成剪映交接包

Use only `cut`, `fade`, and `fade-black`. Static approved titles may remain in FFmpeg. Use Remotion only if captions, graphics, or an explicitly animated title exists, and only if `REMOTION_LICENSE_KEY` is already non-empty; do not invent or set a free license key.

Write derived material only under the job's `work/`, `output/`, or optional `handoff-jianying/`. Rendering creates `work/base.mp4`, `output/preview.mp4`, and `output/edit-report.json`; it is not a QC stage. On feedback, retain prior previews and approvals, create a revision directory, rerender only affected artifacts, and obtain a new approval before editing.

Read [references.md](references.md) for commands, recovery, license handling, and the optional Jianying handoff.
