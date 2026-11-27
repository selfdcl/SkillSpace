# SkillSpace

个人开发的技能集合。当前收录航拍素材入库、编导、剪辑与快速粗剪。

| 技能 | 输入 | 产物 |
| --- | --- | --- |
| [航拍零件化](aerial-parts-ingest/SKILL.md) | 原始航拍素材 | 候选片段、零件库和 library.json |
| [航拍编导](aerial-video-director/SKILL.md) | 已校验的零件库、剪辑需求和本地音乐 | 分镜、调色对照和节奏预览 |
| [航拍剪辑](aerial-video-editor/SKILL.md) | 零件库及已确认的编导方案 | 审核片、确认后的成片和可选剪映交接包 |
| [航拍快速粗剪](aerial-parts-assemble/SKILL.md) | 零件库和主题 | 快速粗剪 |

## 使用

克隆仓库后，打开对应的 SKILL.md，或让支持本地文件访问的助手读取它。文档中的代码示例从仓库根目录运行。请保留各技能与 aerial-parts-shared 的相对位置。

基础流程需要 Python 3.10+、FFmpeg 和 FFprobe。编导依赖通过下面的命令安装。

~~~powershell
python -m pip install -r aerial-parts-shared/requirements-director.txt
~~~

动画标题、字幕和图层的可选 Remotion 渲染还需要 Node.js、npm 和适用的 Remotion 许可。安装依赖时在 aerial-parts-shared/remotion 下运行 npm ci，并在调用渲染的环境中设置 REMOTION_LICENSE_KEY。

原片和本地授权音乐由使用者提供。把每次运行的候选库、方案和成片放在自己的工作目录。

## 验证

~~~powershell
python -X utf8 -m unittest discover -s aerial-parts-shared/tests
~~~
