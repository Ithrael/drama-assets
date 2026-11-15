# 幕间 · 视频人物资产

支持两种使用方式：**作为 Skill 调用**，或**部署项目后通过网页 / HTTP API 使用**。默认覆盖视频中全部可识别角色，为每位角色制作五类资产，最终生成离线展示大屏和 ZIP。

**★ 推荐使用具备视觉理解和生图能力的 AI 大模型或对话环境，并支持携带多张参考图生成 / 编辑图片。** 当前对话模型负责分析原片，生图工具负责制作资产；仅有文本分析能力无法完成全部图片资产。独立 API 模式可分别配置视觉模型和图像编辑模型。

## Skill 调用

项目根目录的 [SKILL.md](SKILL.md) 是技能入口。先按下方「项目部署使用」安装 Python 依赖，再将项目链接到 Codex 的技能目录：

```sh
mkdir -p ~/.codex/skills
ln -s /绝对路径/drama-assets ~/.codex/skills/drama-assets
```

在具备图像生成工具的 Codex 对话中调用：

```text
使用 $drama-assets 分析 /绝对路径/视频.mov
```

默认交付全部角色的：情绪九宫格、上半身图、全身图、正侧背三视图、角色设定图，以及全部角色的展示大屏和资产 ZIP。用户可以明确限定角色或类型。

分析由当前对话模型读取本地采样图片后完成，不另开模型、不要求视觉 API Key。图片生成使用当前环境可用的图像生成工具；分析模型本身不会凭空输出图片。缺少图像能力时记录具体缺项，不能把提示词或原片裁切冒充生成结果。

确定性处理由 `scripts/drama_assets.py` 执行。以下命令在项目根目录运行：

```sh
.venv/bin/python scripts/drama_assets.py prepare --video '/绝对路径/视频.mov'
.venv/bin/python scripts/drama_assets.py import-analysis --project <ID> --json '/项目目录/analysis.json'
.venv/bin/python scripts/drama_assets.py plan --project <ID>
.venv/bin/python scripts/drama_assets.py import-asset --project <ID> --character 01 --kind half --image '/上半身基准图.png'
.venv/bin/python scripts/drama_assets.py review-identity --project <ID> --character 01 --accepted --note '对照原片核对五官、发型与衣装'
.venv/bin/python scripts/drama_assets.py plan --project <ID>
.venv/bin/python scripts/drama_assets.py import-asset --project <ID> --character 01 --kind expressions --image '/表情九宫格.png'
.venv/bin/python scripts/drama_assets.py finalize --project <ID>
```

脚本不会调用模型。`prepare` 按 1 秒间隔并结合场景切换抽帧，保存实际 PTS 时间戳，保留原分辨率原帧，并制作带编号的联系表供当前模型查看。识别人数不设 8 人上限。采样不等于逐帧穷尽，短暂出场、严重遮挡和无法区分的背景人群仍需补看或在覆盖说明中记录。

`plan` 先返回上半身基准任务；全部角色的基准导入并通过原片相似度核对后，才返回其余四类缺失资产及多张参考图、提示词。上方命令展示单个角色的导入过程，需为其他角色及资产重复执行。`finalize` 默认要求每位角色的五类资产齐全且基准审核通过；明确需要部分成果时才用 `--allow-incomplete`。数据格式见 [references/workflow.md](references/workflow.md)。

## 项目部署使用

在安装了 Python 3.11 和 `uv` 的环境中，进入项目目录后执行：

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-web.txt
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 即可上传视频、查看角色、预览资产、打开展示大屏及下载 ZIP。已有 `.venv` 可直接安装 Web 依赖。也可以用 Python 自带的 `venv` 和 `pip` 完成同样的依赖安装。音频工具 `extract_audio.py` 及其依赖保持独立。

部署后的网页支持以下两种执行方式。

### 当前对话 · Skill（★推荐）

1. 上传 MP4、MOV、WebM、MKV 或 M4V（不超过 1 GB / 60 分钟）。网页先提取 6–24 张概览帧。
2. 「分析角色」生成待处理任务与 Skill 指令；复制到 Codex 当前对话，即可用当前模型继续。Skill 会先补充密集采样。
3. 当前对话写回分析后，网页自动更新角色。默认勾选全部角色和全部资产，也可以指定生成范围。
4. 生成按钮同样提供 Skill 指令；生成工具的实际图片导入后可预览、下载和导出。
5. 「展示大屏」打开全体角色的展示页面；部分素材未完成时如实显示缺项。

网页无法在没有对话调用入口的情况下自行触发当前聊天模型。任务登记与模型执行是两个步骤，页面不会把排队状态显示为模型正在分析。

### 独立 API 调用

需要网页独立全自动运行时，可在「调用方式」切换为「独立 API 调用」，填写 API 地址、Key、视觉模型和图像编辑模型。使用兼容 OpenAI 的 `POST /chat/completions` 以及携带多张原片参考图的 multipart `POST /images/edits`；支持图像返回 `b64_json` 或 HTTPS URL。默认 Skill 路径不使用这些接口。

API Key 仅保存在服务进程内存。外部服务也可用 `AI_BASE_URL`、`AI_API_KEY`、`AI_VISION_MODEL`、`AI_IMAGE_MODEL` 环境变量配置；仍需明确切换到 API 模式。只支持文生图、不支持参考图编辑的模型不适用于当前流程。

## 展示大屏和资产包

`output/studio/<ID>/dashboard.html` 是可直接离线打开的单文件大屏，图片嵌入文件内，无外部脚本、字体或 CDN 依赖。支持角色搜索、资产类型筛选、原图放大、下载及全屏展示。

`character-assets.zip` 包含大屏、所有角色参考图与已生成图片、JSON 人物设定、提示词、采样时间戳、人物边界与覆盖说明。完整性针对已识别角色的五类资产，不代表证明原片没有任何识别遗漏。

九种情绪固定为：平静、喜悦、悲伤、愤怒、惊讶、恐惧、厌恶、轻蔑、害羞。九宫格、三视图和设定图各为一张合成 PNG。身份一致性和布局需要人工检查；原片未展示的背面、比例与衣装细节属于推测补全。

## HTTP 入口

| 请求 | 用途 |
| --- | --- |
| `POST /api/upload` | multipart `file` 上传视频，返回项目 ID |
| `GET /api/projects/<ID>` | 项目进度、人物、图片及待处理指令 |
| `POST /api/projects/<ID>/analyze` | 当前对话模式登记任务；API 模式启动分析 |
| `POST /api/projects/<ID>/generate` | JSON `character_ids`、`kinds` 指定生成范围 |
| `GET /api/projects/<ID>/dashboard` | 生成并打开展示大屏 |
| `GET /api/projects/<ID>/download` | 生成并下载资产 ZIP |

这是本机单用户工具，请保持默认 `127.0.0.1` 监听地址。Skill 与 Web 共用项目 JSON；重启后可续做已完成部分。已生成资产的项目不能重新分析覆盖角色，需新建项目。CLI 导入同类图片默认拒绝覆盖，可用 `--replace` 明确替换。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check web/app.js
```

人物相似度流程：分析返回每位角色多张原片的独立裁切区域，生成时实际携带全部原片参考。Skill 先生成上半身基准，以 `review-identity --accepted --note ...` 核对原片五官、发型与服饰后，再生成其余四类；未通过的基准不会作为完整成果导出。文件数量和布局校验与人物相似度审核分开记录。多张原片参考随 ZIP 一并导出。
