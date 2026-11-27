---
name: aerial-parts-ingest
description: >-
  将无人机航拍长素材零件化：扫描文件夹、抽帧、切出不超过 6 秒的可用片段并写入 library.json。
  Use when ingesting drone footage, building a B-roll / selects library, tagging aerial clips,
  or the user mentions 零件化、入库、航拍素材切片、镜头库.
---

# 航拍零件化（入库）

把原始航拍切成可复用零件。本技能**不排成片、不叠化、不配乐**。成片用 `aerial-parts-assemble`。

## 路径

命令从 SkillSpace 仓库根目录运行。可以从本技能实际所在目录向上一层定位仓库根目录。

- 共享脚本：`aerial-parts-shared/scripts`
- Schema：`aerial-parts-shared/library.schema.json`
- 词表：`aerial-parts-shared/vocab.md`

先确认 `ffmpeg` / `ffprobe` 在 PATH。没有则让用户执行 `winget install Gyan.FFmpeg` 并重开终端。

把 `SCRIPTS` 设为上面的 scripts 目录。所有命令用该目录下的 `.py`，不要手写临时 ffmpeg 脚本。

## 硬规则

- 原片只读，禁止覆盖、删除源文件
- 默认直接引用原片的绝对路径，项目目录只保存派生产物；禁止默认复制原片或创建 `input/`
- 只有用户明确要求“备份原片”时才复制。备份后仍保留 `src` 指向原片，并单独记录备份路径
- 单段零件 **≤ 6 秒**；默认切 **3–5 秒**；俯冲 **2–3 秒**
- 同一长运镜切成多段零件，禁止一段超过 6 秒
- 长运镜不能只取开头。连续变化超过 6 秒时，覆盖其起势、发展、高潮、收束
- 相邻抽帧变化幅度接近，表示运镜仍在连续发展，不能仅因主体相同判为重复
- 视觉仍在变化的长运镜，零件间未覆盖空档不得超过 2 秒
- 只有“变化分很低且构图近似”时才能丢弃连续区间
- `废片` 不入库；`library.json` 的 `quality` 只能是 `可用` 或 `勉强`
- 默认只截取 `quality: 可用`；`quality: 勉强` 仅保留在候选清单，只有用户明确要求“包含勉强镜头”时才截取
- `shot` / `light` 必须用词表枚举，见 [vocab.md](../aerial-parts-shared/vocab.md)
- 默认使用变化曲线和窗口计划自动生成候选，不抽帧、不逐帧人工判片；自动窗口候选标记为 `quality: 可用`、`shot/light: 未定`，并注明未经人工判片
- 只有用户明确要求“人工判片”“精筛”或“看图挑选”时才抽帧并做视觉判片；人工模式下，没看过的抽帧不准写进零件
- 先写候选 JSON 给用户确认，再 `cut_part.py`

## 复用的已验证能力

| 步骤 | 用什么 | 来源 |
|---|---|---|
| 盘点 | `ffprobe -print_format json` | ffmpeg 官方 |
| 可选砍头尾抖 | DroneTrim CLI（光流，copy 模式） | [rai0603/DroneTrim](https://github.com/rai0603/DroneTrim) |
| 抽帧 | 间隔 JPEG + 时间码文件名 | [video-frames-skill](https://github.com/mugnimaestra/video-frames-skill) 同类做法 |
| 切片 | ffmpeg `-ss/-to`；`copy` 快、`encode` 帧准 | LosslessCut / ffmpeg 惯例 |
| 校验 | `validate_library.py` | 本仓库 schema |

DroneTrim 官方偏 macOS/Linux。Windows 上若未安装，**跳过**，改用抽帧判断起飞/降落废段，不要强行跑。

## 工作流

复制并勾选：

```
- [ ] 1. probe 盘点
- [ ] 2. （可选）DroneTrim 头尾
- [ ] 3. analyze_changes 计算相邻帧变化
- [ ] 4. plan_windows 规划自动窗口
- [ ] 5. candidates_from_windows 生成候选（先给用户看）
- [ ] 5a. （仅用户要求）extract_batch + 人工判片并精调候选
- [ ] 6. 用户确认后 cut_candidates（默认跳过“勉强”）
- [ ] 7. 写 library.json 并 validate
```

### 1. 盘点

直接对原片所在目录盘点，不要先把素材复制进项目：

```text
python aerial-parts-shared/scripts/probe.py --input <原片或素材文件夹> --output <项目>/inventory.json
```

单片任务直接传原片文件，批量任务传素材文件夹。核对 `video_count`：单片必须为 1，批量必须与文件夹内视频数一致；对不上先停。`inventory.json` 的 `source_dir` 和 `videos[].path` 必须保留原片的绝对路径。

若用户明确要求备份原片，复制到用户指定的备份目录，并在项目说明中记录 `original_source` 与 `backup_source`；不要用备份路径替换精调所需的原始 `src`。

### 2. 可选：DroneTrim

若用户已克隆 DroneTrim 且是 macOS/Linux：

```text
python drone_trim.py <素材文件夹> -o <项目>/trimmed --mode copy --dry-run
```

通过后再去掉 `--dry-run`。后续抽帧改对 `trimmed/`。Windows 默认跳过本步。

### 3. 变化分析与窗口规划

使用 FFmpeg 的 difference frame + `signalstats`，生成客观变化曲线：

```text
python aerial-parts-shared/scripts/analyze_changes.py --input <原片> --output <项目>/changes.json --interval 2
```

生成覆盖长运镜的候选窗口（每段 5 秒，空档最多 2 秒）：

```text
python aerial-parts-shared/scripts/plan_windows.py --changes <项目>/changes.json --output <项目>/window-plan.json
```

### 4. 默认：自动候选

默认不抽帧、不看图，直接从稳定变化区间生成候选：

```text
python aerial-parts-shared/scripts/candidates_from_windows.py --inventory <项目>/inventory.json --window-plan <项目>/window-plan.json --output <项目>/candidates.json
```

自动模式无法判断主体、光线、抖动、过曝或起降废段，因此使用标签：`shot/light/subject: 未定`、`quality: 可用`，并在 `note` 标明未人工判片。这里的“可用”表示通过自动窗口规则、可进入默认截取，不代表经过人工视觉确认。**停下来等用户确认。**

### 5. 可选：人工判片

仅当用户明确要求“人工判片”“精筛”或“看图挑选”时执行本节。

#### 抽帧

航拍是长镜头，**不要用场景检测当主策略**（PySceneDetect 认硬切）。固定间隔：

```text
python aerial-parts-shared/scripts/extract_batch.py --inventory <项目>/inventory.json --out-dir <项目>/frames --interval 2
```

默认 **每 2 秒 1 张、不限制张数**，覆盖全片。长片图会多、抽帧会慢，这是为了判运镜更准。

每条素材一个子目录，含 `*_frames.json`。

`change` 越高表示相邻两张画面变化越大。连续数值相近可视为同一稳定运镜的候选区间；突变可能是运镜变速、转向、曝光变化或抖动，必须回看 JPEG。

窗口计划用于防止遗漏后半段，不代表每个窗口都必须入库。人工模式逐窗看 JPEG，删除抖动/重复，保留构图持续发展的窗口。

#### 判片

读取每个 `*_frames.json` 和对应 JPEG：

- 标 `shot` / `subject` / `light` / `move` / `quality`
- 起飞、降落、抖动、过曝、死黑、地平线严重倾斜 → 不入库
- 可用段给出 `in`/`out`（秒，浮点），`out - in ≤ 6`
- `note` ≤ 40 字，只写图里有的

#### 长运镜拆分

- `≤ 6s`：可作为一个零件
- `6–12s`：通常拆 2 个零件，至少比较前半与后半，保留揭示完成的一段
- `12–24s`：通常拆 3–5 个零件，覆盖起势、发展、高潮、收束
- `> 24s`：按 4–6 秒窗口连续铺开，再删掉真正静止或构图近似的窗口
- 每个零件写可选字段 `motion_group`（同一长运镜共用）和 `phase`：
  `起势`、`发展`、`高潮`、`收束`
- 精华优先级：主体完整出现 / 画面层次最丰富 / 揭示完成 / 构图最稳。禁止默认取最前 5 秒
- 相邻图变化幅度差不多时，优先连续分段保留；变化幅度接近零且构图相同才去重

输出候选列表（还不是成库）：

```json
{
  "id": "sel_0012_a",
  "src": "D:/footage/DJI_0012.MP4",
  "in": 72.0,
  "out": 76.2,
  "shot": "拉升",
  "subject": "海岸线",
  "light": "日出",
  "move": "由低到高",
  "quality": "可用",
  "note": "海平线水平，右侧礁石"
}
```

写回 `candidates.json` 后，**停下来等用户确认。**

### 6. 切片

确认后批量截取；默认只切 `quality: 可用`，自动跳过 `quality: 勉强`：

```text
python aerial-parts-shared/scripts/cut_candidates.py --candidates <项目>/candidates.json --out-dir <项目>/parts --mode encode
```

只有用户明确要求包含“勉强”镜头时，才加：

```text
--include-marginal
```

单条返工仍可使用 `cut_part.py`。

精调仍保留 `src/in/out` 指向原片。零件文件给技能 B 快速拼接。

### 7. 写库并校验

`library.json`：

```json
{
  "schema": "aerial-parts/v1",
  "created": "2026-08-20T12:00:00Z",
  "source_dir": "D:/footage",
  "parts_dir": "D:/project/parts",
  "notes": "",
  "parts": []
}
```

`source_dir` 和每条 `src` 指向真实原片位置，`file` 写成零件 mp4 的绝对路径。然后：

```text
python aerial-parts-shared/scripts/validate_library.py <项目>/library.json --check-files
```

必须打印 `OK`。失败则修 JSON / 重切，禁止进入技能 B。

## 完成时告诉用户

- 零件条数、废片未入库数量
- `library.json` 路径（技能 B 只认这个文件）
- 缺哪类运镜（例如没有「俯冲」），方便补拍或补切
