#!/usr/bin/env python3
"""Skill 的确定性步骤；视觉判断由当前对话模型完成，此脚本不调用模型。"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
from PIL import Image, ImageDraw


def sheets(job):
    folder = server.DATA / job["id"]
    paths = []
    for offset in range(0, len(job["frames"]), 15):
        group = job["frames"][offset:offset + 15]
        width, height = 240, 330
        canvas = Image.new("RGB", (5 * width, math.ceil(len(group) / 5) * height), "#202531")
        draw = ImageDraw.Draw(canvas)
        for j, frame in enumerate(group):
            left, top = (j % 5) * width, (j // 5) * height
            with Image.open(folder / Path(frame["url"]).name) as picture:
                picture.thumbnail((width - 8, height - 28))
                canvas.paste(picture, (left + (width - picture.width) // 2, top + 25))
            draw.text((left + 8, top + 7), f"#{frame['index']:03d}   {frame['seconds']:.2f}s", fill="white")
        path = folder / f"contact-{offset // 15:03d}.jpg"
        canvas.save(path, quality=90)
        paths.append(str(path))
    return paths


def prepare(video=None, project=None, interval=1):
    if interval <= 0 or not math.isfinite(interval):
        raise ValueError("采样间隔必须是有限正数。")
    if project:
        job = server.get_job(project)
        if job["status"] in ("extracting", "analyzing", "generating", "awaiting_generation") or any(c["assets"] for c in job["characters"]):
            raise ValueError("项目正在处理或已有资产；请复用已有采样，或从视频新建项目。")
        source = server.DATA / job["id"] / job["video_file"]
    else:
        source = Path(video).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
            raise ValueError("请选择有效视频文件。")
        if source.stat().st_size > 1024 ** 3:
            raise ValueError("视频请控制在 1 GB 以内。")
        metadata = server.probe(source)
        jid = uuid.uuid4().hex
        folder = server.DATA / jid
        folder.mkdir()
        filename = "source" + source.suffix.lower()
        shutil.copy2(source, folder / filename)
        source = folder / filename
        job = {"id": jid, "name": Path(video).name, "video_file": filename, "size": source.stat().st_size,
               "video_url": f"/media/{jid}/{filename}", "metadata": metadata,
               "status": "frames_ready", "frames": [], "characters": [], "progress": 0, "error": None}
    folder = server.DATA / job["id"]
    # 同时保留定时采样和镜头切换帧，记录 showinfo 提供的实际时间戳。
    expression = f"select=isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval})+gt(scene\\,0.30),showinfo"
    result = subprocess.run([server.imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "info",
                             "-i", str(source), "-vf", expression, "-q:v", "2", "-fps_mode", "vfr", "-start_number", "0",
                             "-y", str(folder / "frame-%05d.jpg")], capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise ValueError("视频采样失败：" + result.stderr[-1200:])
    times = re.findall(r"\bpts_time:([\d.]+)", result.stderr)
    frames = [{"index": i, "seconds": round(float(t), 3), "url": server.media(job, f"frame-{i:05d}.jpg")}
              for i, t in enumerate(times) if (folder / f"frame-{i:05d}.jpg").is_file()]
    if len(frames) != len(times) or not frames:
        raise ValueError("采样文件与时间戳不匹配，未写入角色分析。")
    job.update(frames=frames, metadata=server.probe(source), characters=[], status="frames_ready",
               message="等待当前对话模型查看采样帧", progress=100,
               sampling={"interval_seconds": interval, "scene_threshold": 0.30, "timestamps": "decoded-pts"},
               requested_scope={"characters": "all", "kinds": list(server.KINDS)}, require_identity_review=True, error=None)
    job.pop("pending_request", None)
    server.update(job)
    contact_sheets = sheets(job)
    return {"id": job["id"], "project_file": str(folder / "project.json"),
            "frame_count": len(frames), "contact_sheets": contact_sheets}


def register_asset(job, cid, kind, source, replace=False):
    if job["status"] in ("extracting", "analyzing", "generating"):
        raise ValueError("请等待当前任务完成。")
    character = next((c for c in job["characters"] if c["id"] == cid), None)
    if not character or kind not in server.KINDS:
        raise ValueError("角色编号或资产类型不存在。")
    if kind in character["assets"] and not replace:
        raise ValueError("该资产已存在；确认替换时加 --replace。")
    filename = f"{cid}-{kind}.png"
    with Image.open(source) as picture:
        if min(picture.size) < 256:
            raise ValueError("人物资产边长至少为 256 像素，请导入生成原图。")
        picture.convert("RGB").save(server.DATA / job["id"] / filename)
    character["assets"][kind] = {"url": server.media(job, filename), "label": server.KINDS[kind][0],
                               "generated": True, "tool": "conversation-image-tool",
                               "prompt": server.asset_prompt(character, kind),
                               "reference_images": [server.media(job, p.name) for p in server.reference_paths(job, character)]}
    if kind == "half":
        character["identity_review"] = {"status": "pending"}
    pending = job.get("pending_request")
    done = pending and all(k in c["assets"] for c in job["characters"] if c["id"] in pending["character_ids"] for k in pending["kinds"])
    if done:
        job.pop("pending_request", None)
    server.update(job, status="awaiting_generation" if pending and not done else "ready", error=None)


def scope(job):
    pending = job.get("pending_request")
    requested = pending if pending and pending["action"] == "generate" else job.get("requested_scope", {})
    return requested.get("character_ids", [c["id"] for c in job["characters"]]), requested.get("kinds", list(server.KINDS))


def plan(job):
    selected, kinds = scope(job)
    pending_review = job.get("require_identity_review") and any(
        c.get("identity_review", {}).get("status") != "accepted" for c in job["characters"] if c["id"] in selected)
    return [{"character_id": c["id"], "name": c["name"], "kind": k,
             "reference_path": str(server.DATA / job["id"] / Path(c["reference"]).name),
             "reference_paths": [str(p) for p in server.reference_paths(job, c)],
             "prompt": server.asset_prompt(c, k)}
            for c in job["characters"] if c["id"] in selected for k in (["half"] if pending_review else kinds)
            if (k not in c["assets"] or pending_review and c.get("identity_review", {}).get("status") == "rejected")
            and (not pending_review or c.get("identity_review", {}).get("status") != "accepted")]


def review_identity(job, cid, accepted, note):
    character = next((c for c in job["characters"] if c["id"] == cid), None)
    if not character or "half" not in character["assets"] or not note.strip():
        raise ValueError("先生成上半身基准，并填写与原片对照的核对说明。")
    character["identity_review"] = {"status": "accepted" if accepted else "rejected", "note": note,
                                    "baseline_sha256": __import__("hashlib").sha256(
                                        (server.DATA / job["id"] / Path(character["assets"]["half"]["url"]).name).read_bytes()).hexdigest()}
    server.update(job)


def finalize(job, allow_incomplete=False):
    selected, kinds = scope(job)
    missing = [f"{c['id']}/{k}" for c in job["characters"] if c["id"] in selected for k in kinds
               if k not in c["assets"] or not (server.DATA / job["id"] / Path(c["assets"][k]["url"]).name).is_file()]
    if not job["characters"]:
        raise ValueError("尚未写入角色分析，不能导出成果。")
    if job.get("require_identity_review") and not allow_incomplete:
        unreviewed = [c["id"] for c in job["characters"] if c["id"] in selected and c.get("identity_review", {}).get("status") != "accepted"]
        if unreviewed:
            raise ValueError("人物相似度基准尚未通过核对：" + ", ".join(unreviewed))
    if missing and not allow_incomplete:
        raise ValueError("全部资产尚未完成：" + ", ".join(missing))
    if job["status"] in ("extracting", "analyzing", "generating"):
        raise ValueError("请等待当前任务完成。")
    board = server.build_dashboard(job)
    archive = server.download(job["id"])
    return {"complete": not missing, "missing": missing, "scope": {"character_ids": selected, "kinds": kinds}, "dashboard": str(board),
            "dashboard_url": f"http://127.0.0.1:8000{job['dashboard_url']}", "archive": str(archive.path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare", help="密集抽帧并制作供当前模型查看的联系表")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--video")
    group.add_argument("--project")
    p.add_argument("--interval", type=float, default=1)
    commands.add_parser("pending", help="列出网页等待当前对话处理的任务")
    for name in ("show", "sheets", "import-analysis", "plan", "import-asset", "review-identity", "finalize"):
        p = commands.add_parser(name)
        p.add_argument("--project", required=True)
        if name == "import-analysis":
            p.add_argument("--json", required=True)
        elif name == "import-asset":
            p.add_argument("--character", required=True)
            p.add_argument("--kind", choices=list(server.KINDS), required=True)
            p.add_argument("--image", required=True)
            p.add_argument("--replace", action="store_true")
        elif name == "finalize":
            p.add_argument("--allow-incomplete", action="store_true")
        elif name == "review-identity":
            p.add_argument("--character", required=True)
            p.add_argument("--accepted", action="store_true")
            p.add_argument("--note", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.video, args.project, args.interval)
        elif args.command == "pending":
            result = [j for p in server.DATA.glob("*/project.json")
                      if (j := json.loads(p.read_text())).get("pending_request")]
        else:
            job = server.get_job(args.project)
            if args.command == "show":
                result = job
            elif args.command == "sheets":
                result = sheets(job)
            elif args.command == "import-analysis":
                analysis = json.loads(Path(args.json).read_text())
                server.apply_characters(job, analysis["characters"], coverage_note=analysis.get("coverage_note", ""))
                result = {"id": job["id"], "characters": len(job["characters"]), "engine": "current-conversation"}
            elif args.command == "plan":
                result = plan(job)
            elif args.command == "import-asset":
                register_asset(job, args.character, args.kind, args.image, args.replace)
                result = {"ok": True, "remaining": len(plan(job))}
            elif args.command == "review-identity":
                review_identity(job, args.character, args.accepted, args.note)
                result = {"ok": True, "remaining": len(plan(job))}
            else:
                result = finalize(job, args.allow_incomplete)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        parser.exit(1, f"处理失败：{error}\n")


if __name__ == "__main__":
    main()
