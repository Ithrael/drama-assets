---
name: drama-assets
description: 从视频抽取角色并生成人物资产。用于视频人物拆解、角色资产包和人物展示大屏；直接使用当前对话模型分析，默认覆盖全部可识别角色、每位角色全部五类资产，输出离线大屏和 ZIP。也可接续幕间网页中的待处理项目。
---

# 幕间人物资产

Skill 根目录就是本项目目录；以下 `<root>` 表示读取此文件后的真实目录（安装路径可能是符号链接）。脚本与 Web 工作台共用 `output/studio/`。

默认完成**全部可识别角色 × 全部五类人物资产 → 展示大屏 + ZIP**。用户指定角色或类型时按其范围执行。不要默认缩成两名主角、样片或少量资产。

## 分析视频

使用当前对话模型直接看图、判断和描述。**不调用视觉分析 API，不启动 `codex exec`，不要求分析 Key，不通过其他模型或子任务替代当前模型。** Python 只做解码、抽帧、裁切、记录与打包。

先确保 `<root>/.venv/bin/python` 可用；缺依赖时用 `uv pip install --python <root>/.venv/bin/python -r <root>/requirements-web.txt`，缺虚拟环境时先创建 Python 3.11 环境。

新视频：

```sh
<root>/.venv/bin/python <root>/scripts/drama_assets.py prepare --video '/绝对路径/视频.mov'
```

这会按默认 1 秒间隔结合场景切换抽帧，输出项目 ID、实际时间戳和带编号的联系表。用可用的本地图片查看工具读取**所有联系表**；身份、衣装或遮挡不清时打开对应原帧，必要时用 FFmpeg 在相关时间段补看，不把均匀采样宣称为逐帧穷尽。

合并同一人物在不同镜头中的出现，包含可清楚区分的配角；无法区分的背景人群只记录覆盖限制，不编造独立角色。不猜演员真实身份或原片没有依据的姓名。角色描述聚焦五官、发型、服装、配色、配饰与可见体型。

在项目目录写入 `analysis.json`，结构与坐标说明见 [references/workflow.md](references/workflow.md)，然后：

```sh
<root>/.venv/bin/python <root>/scripts/drama_assets.py import-analysis --project <ID> --json '<项目目录>/analysis.json'
<root>/.venv/bin/python <root>/scripts/drama_assets.py plan --project <ID>
```

采样帧保留原分辨率；联系表用于找镜头，不能把缩略图当作生成输入。为每位角色优先找脸部清楚的近景，结合不同时间和角度的原片参考，在 `references` 中分别填写各帧的框。不能只记录多个帧编号、实际只传一张。发型和五官描述须有原片依据，不能因古装题材添加发髻或发冠。

导入后查看全部人物裁切参考，确认没有裁错人。`plan` 的 `reference_paths` 是必须实际传入图像工具的多张原片文件，不使用旧版生成脸作为身份基准。

## 制作全部人物资产

五类固定为：`expressions` 情绪九宫格（平静、喜悦、悲伤、愤怒、惊讶、恐惧、厌恶、轻蔑、害羞）；`half` 上半身；`full` 全身；`views` 正侧背三视图；`sheet` 角色设定图（人物、服装细节、配饰、配色）。每类独立图片，九宫格和三视图各自为一张合成图。

按 `plan` 分两阶段执行，当前环境有内置图像生成/编辑工具时读取适用的 imagegen Skill 并使用它。

先为每位角色生成 `half` 上半身基准。将生成图与多张原片核对脸型、眼型、眉位、鼻唇、下颌、发际线、发型、年龄感和服装。远景、侧脸及遮挡可能导致误判，不能用泛化的古装美男或美女代替原片人物。通过后由当前模型记录实际核对说明，无需让用户逐人确认：

```sh
<root>/.venv/bin/python <root>/scripts/drama_assets.py review-identity --project <ID> --character <角色ID> --accepted --note '与哪些原帧对照，五官、发型及服装的核对结果与局限'
```

不相似时去掉 `--accepted` 记录问题，补充原片参考后重做基准；替换导入使用 `--replace`。不能让有偏差的基准扩散到整组生成。所有基准通过后再次 `plan`，才会给出其余资产。

每张图都携带 `reference_paths` 中的原片参考；生成的基准用于对照审核，不能取代原片成为后续人脸依据。不要用不同裁切冒充新表情，不用其他角色资产填空，不把未展示的背面说成已还原事实。

生成工具产出实际文件后，通过下列命令导入（保留原始生成图）：

```sh
<root>/.venv/bin/python <root>/scripts/drama_assets.py import-asset --project <ID> --character <角色ID> --kind <类型> --image '/生成图绝对路径.png'
```

确认图片格式、九宫格数量、三视图角度，并再次检查与原片的相似度及发型。若工具不能提供可保存的图像，或生成能力不可用，保留已完成部分并说明具体缺项；不降级为假图或把提示词当作已生成资产。用户明确指定外部生成服务时才使用对应服务。

## 展示与交付

全部角色资产完成后执行：

```sh
<root>/.venv/bin/python <root>/scripts/drama_assets.py finalize --project <ID>
```

默认拒绝把缺少资产的项目当作完整成果。遇到确切阻塞仍可加 `--allow-incomplete` 导出部分大屏，同时如实报告缺项；不要将其描述为任务完成。

输出 `dashboard.html` 为自包含离线大屏：全部角色、五类图片、按角色搜索、按类型筛选、放大预览和全屏展示；ZIP 同时包含大屏、参考图、生成图和来源 JSON。查看大屏，检查图片加载与筛选，再向用户交付实际文件链接。需要网页时启动 `<root>/.venv/bin/python -m uvicorn server:app --app-dir <root> --host 127.0.0.1 --port 8000`，通过输出的本地 URL 查看。

## 接续网页项目

网页默认「当前对话」方式，按钮只登记待处理任务，不能直接调用当前聊天。用户在对话中请求继续时执行 `scripts/drama_assets.py pending`，或 `show --project <ID>` 读取其指定项目；多项且无法判断目标时先问。

对于待分析项目，先 `prepare --project <ID>` 补充密集采样，再走上述分析与生成流程。对于已有角色的生成请求，直接用 `plan`，遵守 `pending_request` 的角色及类型范围。结果写回后网页自动刷新；网页模式仍可由用户明确切换为独立 API 调用。两种方式共用成果结构。
