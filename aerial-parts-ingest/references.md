# 入库补充

## 项目目录建议

```text
<项目>/
  inventory.json
  frames/<stem>/*.jpg
  frames/<stem>/<stem>_frames.json
  parts/<id>.mp4
  library.json
```

原片默认留在原目录，项目内不创建 `input/`。只有用户明确要求备份时才额外复制原片；JSON 中的 `source_dir` / `src` 仍指向原片绝对路径。

## 时长

| 运镜 | 目标 | 上限 |
|---|---|---|
| 拉升 / 环绕 / 横移 / 悬停 | 3–5s | 6s |
| 俯冲 | 2–3s | 6s |

## DroneTrim 要点（可选）

仓库：https://github.com/rai0603/DroneTrim

- 只剪头尾，不切中段
- `--mode copy` 快；进点对齐关键帧，可能多剪 0.5–1s
- 海面/云层/雪地特征点少，会偏保守（少剪）
- 依赖：`opencv-python` `numpy` `ffmpeg`

## 抽帧间隔

默认自动模式不抽帧。只有用户明确要求人工判片/精筛时，才按每 **2 秒 1 张**铺满全片，**不设张数上限**；不要为赶时间把间隔拉到 6 秒。

## 长运镜保留策略

- 相邻抽帧变化幅度相近：视为连续运镜，不是重复画面
- 连续运镜按 4–6 秒窗口覆盖；未覆盖空档不超过 2 秒
- 用 `analyze_changes.py` 生成 `changes.json`，辅助判断稳定区间和变化节点
- 每个阶段都要比较；优先保留主体完整、揭示完成、构图最稳的窗口
- `motion_group` 关联同一长运镜；`phase` 标记起势/发展/高潮/收束

## 抽帧为何不用 PySceneDetect

https://github.com/Breakthrough/PySceneDetect 适合硬切。单段航拍连续运镜几乎没有 scene cut，应用固定间隔抽帧。
