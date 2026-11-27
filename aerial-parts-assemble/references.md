# 出库补充

## edit.json

| 字段 | 含义 |
|---|---|
| `theme` | 用户原话 |
| `target_sec` | 目标秒数 |
| `part_ids` | 有序零件 id，必须存在于 library |
| `transition` | `fade` 或 `none` |
| `xfade` | 叠化秒，默认 0.4 |
| `missing` | 库中没有的需求 |

## ffmpeg 叠化

`assemble.py` 使用官方 `xfade=transition=fade`。多段 offset 公式：

`offset_k = sum(dur[0..k]) - fade * k` 在脚本里按累积 `dur[i] - fade` 实现。

滤镜报错时先 `--transition none` 验证拼接，再开叠化。

## 不要做的事

- 不要读取 `source_dir` 里的长视频
- 不要调用 `extract_frames.py` / `probe.py`
- 不要生成 AI 假航拍代替缺口
