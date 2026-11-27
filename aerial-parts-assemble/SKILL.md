---
name: aerial-parts-assemble
description: >-
  按主题描述，从航拍零件库 library.json 挑选片段并 ffmpeg 拼接成粗剪。
  Use when assembling a drone highlight from tagged parts, 按主题剪辑, 用镜头库出片,
  or after aerial-parts-ingest has produced library.json.
---

# 航拍零件成片（出库）

从已入库零件装配成片。本技能**禁止再分析原始长素材、禁止抽原片的帧**。没有 `library.json` 就停，改走 `aerial-parts-ingest`。

## 路径

命令从 SkillSpace 仓库根目录运行。可以从本技能实际所在目录向上一层定位仓库根目录。

- 脚本：`aerial-parts-shared/scripts`
- 词表：`aerial-parts-shared/vocab.md`

需要 `ffmpeg` / `ffprobe`。

## 硬规则

- 只使用 `library.json` 里的 `id`
- 库里没有的镜头：列出缺口，不要编造、不要去原片里找
- 先写 `edit.json` 给用户确认，再渲染
- 默认转场叠化 **0.4s**；零件时长必须 **> xfade**
- 默认成片 **1920×1080、30fps、无音轨**（航拍电机声默认丢弃）
- 同一 `shot` 不要连续超过 2 条；开场优先 `拉升`，结尾优先 `悬停` 或远景 `拉升`

## 复用的已验证能力

| 步骤 | 用什么 | 来源 |
|---|---|---|
| 检索 | `library.json` 字段过滤 | 本仓库 schema |
| 时间线契约 | `part_ids` 列表 | 类似 [cutpilot](https://github.com/rogerchappel/cutpilot) 的 JSON EDL |
| 渲染 | ffmpeg `xfade` / `concat` | ffmpeg 官方滤镜；命令由 `assemble.py` 生成 |
| 命令手册（排错时） | video-processing-editing / ffmpeg-video-editor Skill | skills.sh 上安装量过千的 FFmpeg Skill |

不把 Shotpilot / SkyCut 当运行时（Windows 不友好或不是 Skill）。

## 工作流

```
- [ ] 1. 读取并 validate library.json
- [ ] 2. 按主题过滤零件
- [ ] 3. 填叙事槽位，写 edit.json
- [ ] 4. 用户确认
- [ ] 5. assemble.py 渲染
```

### 1. 读库

```text
python aerial-parts-shared/scripts/validate_library.py <项目>/library.json --check-files
```

必须 `OK`。

### 2. 过滤

用户会给：主题、时长、画幅。用 `subject` / `light` / `shot` 精确匹配词表，再在 `note` 里补语义。

例：`60 秒海边日出` → 优先 `light=日出|黄金时刻` 且 `subject` 含海/岸/礁。

### 3. 叙事槽位（按目标时长填，宁缺毋滥）

| 顺序 | 槽位 | 优先 shot | 建议时长 |
|---|---|---|---|
| 1 | 开场环境 | 拉升 | 3–5s |
| 2 | 主体 | 环绕 或 横移 | 3–4s |
| 3 | 动态 | 俯冲 | 2–3s |
| 4 | 补充 | 与主题相关的可用件 | 3–5s |
| 5 | 收尾 | 悬停 或 拉升 | 3–5s |

总时长 ≈ 各 `dur` 之和 − `xfade × (镜数-1)`。差超过目标 ±15% 就增删零件，不要变速凑（除非用户明确要求）。

`edit.json`：

```json
{
  "theme": "海边日出 60s",
  "target_sec": 60,
  "aspect": "16:9",
  "transition": "fade",
  "xfade": 0.4,
  "part_ids": ["sel_0012_a", "sel_0015_b", "sel_0018_a"],
  "missing": []
}
```

`missing` 写库里没有但主题需要的镜头。停下来等用户确认。

### 4. 渲染

```text
python aerial-parts-shared/scripts/assemble.py --library <项目>/library.json --edit <项目>/edit.json --out <项目>/output/roughcut.mp4 --transition fade --xfade 0.4 --width 1920 --height 1080 --fps 30
```

先看节奏可用 `--transition none`。4K 最终版把 `--width 3840 --height 2160`。

精调（LUT、BGM、达芬奇）不在本技能内。需要回原片精切时，用零件条目里的 `src/in/out`。

## 完成时告诉用户

- 成片路径、实际时长、用了哪些 `id`
- `missing` 缺口
- 下一句可复制：「打开 roughcut.mp4，要改哪几镜告诉我 part id」
