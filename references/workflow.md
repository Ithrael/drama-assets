# 当前对话的分析结果

`prepare` 返回项目 ID。项目文件 `output/studio/<ID>/project.json` 的 `frames` 数组提供所有帧的 `index`、`seconds`（实际解码 PTS 秒数）和图片路径 `/media/<ID>/frame-00000.jpg`；本地文件位于项目目录。联系表角标标明同样的帧编号。

当前模型查看图片后将以下结构写入该项目的 `analysis.json`：

```json
{
  "characters": [
    {
      "name": "棕衣短发男子",
      "description": "凌乱黑色短发，棕灰交领外袍，暗红内领，腰带和护腕。",
      "frame_index": 0,
      "bbox": [0.05, 0.1, 0.9, 0.95],
      "reference_indices": [0, 8, 24],
      "references": [
        {"frame_index": 0, "bbox": [0.05, 0.1, 0.9, 0.6], "role": "identity"},
        {"frame_index": 8, "bbox": [0.2, 0.15, 0.8, 0.65], "role": "identity"},
        {"frame_index": 24, "bbox": [0.1, 0.05, 0.9, 0.98], "role": "outfit"}
      ]
    }
  ],
  "coverage_note": "记录人物识别中不确定之处、遮挡和无法区分的背景人群。"
}
```

这些坐标仅是结构示例，不是任何视频的实际检测结果。`bbox` 表示最佳参考帧中单个角色的归一化 `[左, 上, 右, 下]`，满足 `0 ≤ 左 < 右 ≤ 1`、`0 ≤ 上 < 下 ≤ 1`。编号必须来自本次项目；`reference_indices` 记录同一角色的其他参考帧。尽量选面部和服装清晰、其他人物少的帧。

命令可从任意目录运行；通过安装位置的真实项目目录定位代码。导入会按人物数组顺序自动编号 `01`、`02`……，不限制为 8 人；同一角色不要重复列出。

`plan --project <ID>` 是未完成资产的清单；重复运行会跳过已经导入的类型。`import-asset` 默认拒绝覆盖，用户要求重制同类图片时可加 `--replace`。若用户只要求分析，导入分析后生成大屏即可：`finalize --allow-incomplete`，明确标明尚未请求图片生成。

覆盖说明应保留在项目 JSON 和最终资产包中；原片参考与生成图片的来源必须区分。`sampling` 记录抽帧间隔、切镜阈值与时间戳来源；完整性判断只针对已识别角色的五类资产，不代表证明视频中绝无短暂遗漏的人物。

每个 `references` 项使用独立原帧与裁切框，首张选脸部最清楚的主参考。导入结果的 `reference_images` 保存路径、时间、框、尺寸和 `generated: false`；`plan.reference_paths` 返回实际传入生成工具的全部原片裁切图。不能只记录多个帧编号而仅使用一张图，也不能用生成增强的人脸代替原片。

Skill 新项目先用 `plan` 生成每人的上半身基准，导入后以 `review-identity --accepted --note ...` 记录与原片的五官、发型和衣装核对。拒绝的基准会保留在待重做清单；替换使用 `--replace`，替换基准会重置审核。全部通过后 `plan` 才展开其余类型，最终导出同时检查相似度审核和资产完整性。
