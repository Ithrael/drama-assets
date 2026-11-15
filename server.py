"""本地人物资产工作台：视频抽帧、视觉分析、带参考图的资产生成。"""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import uuid
import zipfile
from typing import Literal

import httpx
import imageio_ffmpeg
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field
from dashboard import write_dashboard

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "output" / "studio"
DATA.mkdir(parents=True, exist_ok=True)
POOL = ThreadPoolExecutor(max_workers=2)
LOCK = threading.Lock()
JOBS = {}
SETTINGS = {"base_url": os.getenv("AI_BASE_URL", "https://api.openai.com/v1"),
            "execution_mode": "conversation",
            "api_key": os.getenv("AI_API_KEY", ""),
            "vision_model": os.getenv("AI_VISION_MODEL", ""),
            "image_model": os.getenv("AI_IMAGE_MODEL", "")}
KINDS = {
    "expressions": ("情绪九宫格", "A precisely aligned 3 by 3 grid of nine equal head-and-shoulder portraits. Row-major expressions: neutral, happy, sad, angry, surprised, afraid, disgusted, contemptuous, shy. Every cell has the SAME character, costume and camera angle; distinct legible emotions. Thin white gutters; no text."),
    "half": ("上半身图", "One front-facing waist-up portrait, complete head and both shoulders, relaxed hands, natural neutral expression."),
    "full": ("全身图", "One full-body front-facing standing portrait. Entire head, hands and feet visible, generous margins; neutral pose."),
    "views": ("正侧背三视图", "Character turnaround with exactly three equal panels: full-body FRONT, exact SIDE profile, and BACK. Same scale and aligned ground level. Entire head and feet visible in every panel."),
    "sheet": ("角色设定图", "A professional character design reference sheet: a large full-body front view, a waist-up portrait, small side and back views, close-up details of costume, hair, accessories, and a coherent costume color palette. Clean coherent layout. No invented text.")}


def save(job):
    path = DATA / job["id"] / "project.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2))
    temporary.replace(path)


def update(job, **values):
    with LOCK:
        job.update(values)
        save(job)


def get_job(jid):
    if not re.fullmatch(r"[a-f0-9]{32}", jid):
        raise HTTPException(404, "项目不存在")
    with LOCK:
        path = DATA / jid / "project.json"
        if not path.exists():
            raise HTTPException(404, "项目不存在")
        # Skill 与 Web 共用项目文件；空闲项目每次读取，接收当前对话写回的结果。
        if jid not in JOBS or JOBS[jid]["status"] not in ("extracting", "analyzing", "generating"):
            persisted = json.loads(path.read_text())
            if jid in JOBS:
                JOBS[jid].clear()
                JOBS[jid].update(persisted)
            else:
                JOBS[jid] = persisted
        return JOBS[jid]


def media(job, relative):
    return f"/media/{job['id']}/{relative}"


def probe(path):
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                            capture_output=True, text=True, timeout=30)
    duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", result.stderr)
    dimensions = re.search(r"Video:.*? (\d{2,5})x(\d{2,5})(?:[ ,])", result.stderr)
    if not duration or not dimensions:
        raise ValueError("无法解码这个视频，请改用有效的 MP4、MOV 或 WebM 文件。")
    h, m, s = map(float, duration.groups())
    seconds = h * 3600 + m * 60 + s
    if not 0 < seconds <= 3600:
        raise ValueError("请选择时长不超过 60 分钟的视频。")
    return {"duration": seconds, "width": int(dimensions[1]), "height": int(dimensions[2]),
            "has_audio": bool(re.search(r"Stream #.*Audio:", result.stderr))}


def extract(job):
    try:
        folder = DATA / job["id"]
        metadata = probe(folder / job["video_file"])
        update(job, metadata=metadata, message="正在提取关键帧", progress=15)
        count = min(24, max(6, math.ceil(metadata["duration"] / 4)))
        frames = []
        for index in range(count):
            seconds = (metadata["duration"] - 0.1) * index / max(1, count - 1)
            filename = f"frame-{index:02d}.jpg"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-loglevel", "error",
                            "-ss", str(seconds), "-i", str(folder / job["video_file"]),
                            "-frames:v", "1", "-q:v", "2",
                            "-y", str(folder / filename)], check=True, capture_output=True, timeout=45)
            frames.append({"index": index, "seconds": round(seconds, 2), "url": media(job, filename)})
            update(job, frames=frames[:], progress=15 + round(65 * (index + 1) / count))
        update(job, status="frames_ready", progress=100, message="关键帧已就绪，可交给当前对话模型分析")
    except Exception as exc:
        update(job, status="error", error=str(exc), message="视频读取失败")


def config(which):
    with LOCK:
        cfg = SETTINGS.copy()
    if not cfg["api_key"] or not cfg[f"{which}_model"]:
        raise HTTPException(400, "请先在「模型设置」填写 API Key 和对应模型名称。")
    return cfg


def response_json(response):
    if response.is_error:
        # 不回显响应原文，以免网关将请求中的凭证写入错误信息。
        raise ValueError(f"模型服务返回 HTTP {response.status_code}，请检查地址、模型和账户额度。")
    return response.json()


def crop_reference(job, spec):
    index, box = spec["frame_index"], spec["bbox"]
    if type(index) is not int or not 0 <= index < len(job["frames"]):
        raise ValueError("参考帧编号无效。")
    if len(box) != 4 or any(type(v) not in (float, int) or not math.isfinite(v) for v in box):
        raise ValueError("人物位置无效。")
    l, t, r, b = box
    if not (0 <= l < r <= 1 and 0 <= t < b <= 1):
        raise ValueError("人物边界超出参考帧。")
    with Image.open(DATA / job["id"] / Path(job["frames"][index]["url"]).name) as image:
        crop = image.crop((int(l * image.width), int(t * image.height), math.ceil(r * image.width), math.ceil(b * image.height)))
        if min(crop.size) < 20:
            raise ValueError("人物参考区域过小。")
        return crop


def reference_paths(job, character):
    refs = character.get("reference_images") or [{"url": character["reference"]}]
    return [DATA / job["id"] / Path(r["url"]).name for r in refs]


def apply_characters(job, people, engine="current-conversation", coverage_note=""):
    """写入当前对话或 API 的角色分析；两种入口使用同一校验与资产结构。"""
    if job["status"] in ("extracting", "generating", "awaiting_generation"):
        raise ValueError("请等待当前任务完成。")
    if any(c.get("assets") for c in job["characters"]):
        raise ValueError("已有生成资产，请新建项目以保留现有成果。")
    if not isinstance(people, list) or not people:
        raise ValueError("没有有效角色，请补充参考帧后重试。")
    # 先验证完整结果，避免失败时覆盖已有参考图。
    crops = []
    characters = []
    for i, person in enumerate(people):
        index, box = person["frame_index"], person["bbox"]
        cid = f"{i + 1:02d}"
        folder = DATA / job["id"]
        specs = person.get("references") or [{"frame_index": index, "bbox": box, "role": "identity"}]
        if not isinstance(specs, list) or not 1 <= len(specs) <= 6:
            raise ValueError("每个角色请选择1至6张清晰原片参考。")
        # 主参考仍校验；补充参考必须有各自的框，不能把同一个框套到不同镜头。
        crop_reference(job, {"frame_index": index, "bbox": box})
        original_refs = []
        for n, spec in enumerate(specs):
            crop = crop_reference(job, spec)
            filename = f"character-{cid}.png" if n == 0 else f"character-{cid}-ref-{n:02d}.png"
            crops.append((crop, folder / filename))
            original_refs.append({"url": media(job, filename), "frame_index": spec["frame_index"],
                                  "seconds": job["frames"][spec["frame_index"]]["seconds"], "bbox": spec["bbox"],
                                  "role": spec.get("role", "identity"), "dimensions": list(crop.size), "generated": False})
        references = person.get("reference_indices", [index])
        if not isinstance(references, list) or any(type(n) is not int or not 0 <= n < len(job["frames"]) for n in references):
            raise ValueError("补充参考帧编号无效。")
        characters.append({"id": cid, "name": str(person["name"])[:60],
                           "description": str(person["description"])[:2000],
                           "reference": media(job, f"character-{cid}.png"), "frame_index": index,
                           "reference_indices": list(dict.fromkeys([index] + [s["frame_index"] for s in specs] + references)), "bbox": box,
                           "reference_images": original_refs, "identity_review": {"status": "pending"}, "assets": {}})
    with LOCK:
        for crop, path in crops:
            crop.save(path)
        job.update(characters=characters, status="ready", message=f"已识别 {len(characters)} 位角色", progress=100,
                   analysis={"engine": engine, "scope": "all-identifiable-characters", "coverage_note": str(coverage_note)[:8000]}, error=None)
        job.pop("pending_request", None)
        save(job)


def analyze(job, cfg):
    try:
        content = [{"type": "text", "text":
            '分析这些按时间排列的视频帧，找出可清晰区分的主要角色。不要把同一人不同表情算成多人，不要猜演员真实身份。'
            '仅返回 JSON 对象 {"characters":[{"name":"外观称呼","description":"详细可见外观、发型、衣装、配色、配饰",'
            '"frame_index":0,"bbox":[0.1,0.1,0.9,0.95],"reference_indices":[0,1]}]}。'
            '每个人额外返回 references 数组，选择2至4张不同原片帧；每项含 frame_index、独立 bbox、role(identity或outfit)。'
            '先选脸部最大且清晰的正面或三分之二侧面，再选其他角度和服饰参考。发型以可见事实描述，不凭古装补造发髻。'
            'bbox 是最佳参考帧中单个角色的归一化边界 [left,top,right,bottom]；frame_index 必须来自提供的编号。包含全部可识别角色，不限定主角或人数。'}]
        for frame in job["frames"]:
            raw = (DATA / job["id"] / Path(frame["url"]).name).read_bytes()
            content.extend([{"type": "text", "text": f"帧编号 {frame['index']}，时间 {frame['seconds']} 秒"},
                            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(raw).decode()}}])
        with httpx.Client(timeout=240) as client:
            payload = response_json(client.post(cfg["base_url"] + "/chat/completions",
                headers={"Authorization": "Bearer " + cfg["api_key"]},
                json={"model": cfg["vision_model"], "messages": [{"role": "user", "content": content}]}))
        text = payload["choices"][0]["message"]["content"]
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        people = json.loads(text)["characters"]
        apply_characters(job, people, engine="api")
    except Exception as exc:
        update(job, status="frames_ready", error=str(exc), message="角色分析失败，可重试")


def asset_prompt(character, kind):
    return ("Create a photorealistic professional drama character asset. Preserve the EXACT same fictional character identity, "
            "facial features, hairstyle, age, costume, materials and colors as the ORIGINAL VIDEO reference images. "
            "Use ALL supplied original frames for the SAME person's face and costume. Preserve facial asymmetry, eye shape, "
            "brow position, nose, lips, jaw and hairline; no beautification, face slimming, enlarged eyes, invented hair buns or generic actor face. "
            "Generated images are never identity ground truth. "
            f"Character description: {character['description']}. {KINDS[kind][1]} "
            "Plain light gray studio background, soft consistent studio lighting, crisp details, no subtitles, "
            "no watermark, no other characters. Unseen costume and back details may be coherently inferred.")


def build_dashboard(job):
    path = write_dashboard(job, DATA / job["id"], KINDS)
    update(job, dashboard_url=media(job, path.name))
    return path


def request_conversation(job, action, character_ids=None, kinds=None):
    prompt = (f"使用 $drama-assets 处理项目 {job['id']}。直接用当前对话模型分析视频，"
              "抽取全部可识别角色，为全部角色生成全部五类资产，最终生成展示大屏和 ZIP。")
    request = {"action": action, "engine": "current-conversation", "prompt": prompt,
               "character_ids": character_ids or [c["id"] for c in job["characters"]],
               "kinds": kinds or list(KINDS)}
    if action == "generate":
        request["prompt"] = (f"使用 $drama-assets 继续项目 {job['id']}，角色 {', '.join(request['character_ids'])}，"
                             f"生成资产 {', '.join(request['kinds'])}，完成后生成展示大屏和 ZIP。")
    update(job, status="awaiting_" + ("analysis" if action == "analyze" else "generation"),
           requested_scope={"characters": "all", "kinds": list(KINDS)} if action == "analyze" else
                           {"character_ids": request["character_ids"], "kinds": request["kinds"]},
           pending_request=request, progress=0, error=None, message="等待当前对话处理，请复制下方指令到 Codex")
    return request


def generate(job, ids, kinds, cfg):
    total = len(ids) * len(kinds)
    completed = 0
    failures = []
    try:
        for character in job["characters"]:
            if character["id"] not in ids:
                continue
            refs = reference_paths(job, character)
            for kind in kinds:
                label, _ = KINDS[kind]
                update(job, message=f"正在生成 {character['name']} · {label}", progress=round(completed / total * 100))
                prompt = asset_prompt(character, kind)
                try:
                    with httpx.Client(timeout=600, follow_redirects=True) as client:
                        files = [("image" if len(refs) == 1 else "image[]", (p.name, p.read_bytes(), "image/png")) for p in refs]
                        payload = response_json(client.post(cfg["base_url"] + "/images/edits",
                            headers={"Authorization": "Bearer " + cfg["api_key"]},
                            data={"model": cfg["image_model"], "prompt": prompt, "n": "1", "size": "1024x1024"}, files=files))
                        result = payload["data"][0]
                        if result.get("b64_json"):
                            raw = base64.b64decode(result["b64_json"], validate=True)
                        elif result.get("url", "").startswith("https://"):
                            response = client.get(result["url"])
                            response.raise_for_status()
                            raw = response.content
                        else:
                            raise ValueError("模型未返回图片。")
                    filename = f"{character['id']}-{kind}.png"
                    with Image.open(io.BytesIO(raw)) as image:
                        image.convert("RGB").save(DATA / job["id"] / filename)
                    with LOCK:
                        character["assets"][kind] = {"url": media(job, filename), "label": label, "generated": True,
                                                      "prompt": prompt, "model": cfg["image_model"],
                                                      "reference_images": [media(job, p.name) for p in refs], "identity_review": "pending"}
                        if kind == "half":
                            character["identity_review"] = {"status": "pending"}
                        save(job)
                except Exception as exc:
                    failures.append(f"{character['name']} / {label}：{exc}")
                completed += 1
        update(job, status="ready", progress=100, message="资产生成完成" if not failures else "部分资产未生成，可重试",
               error="\n".join(failures) or None)
        build_dashboard(job)
    except Exception as exc:
        update(job, status="ready", error=str(exc), message="生成中断，已完成资产已保存")


@asynccontextmanager
async def lifespan(app):
    # 重启后允许重新执行未完成的模型任务。
    for path in DATA.glob("*/project.json"):
        try:
            job = json.loads(path.read_text())
            if job["status"] in ("extracting", "analyzing", "generating"):
                job.update(status="ready" if job.get("characters") else "frames_ready" if job.get("frames") else "error",
                           error="服务重启中断了任务，请重新执行。")
                save(job)
        except (ValueError, KeyError):
            pass
    yield


app = FastAPI(title="幕间 · 人物资产工作台", lifespan=lifespan)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != str(request.base_url).rstrip("/"):
        return __import__("fastapi").responses.JSONResponse({"detail": "请从本机工作台发起请求"}, status_code=403)
    return await call_next(request)


class SettingsInput(BaseModel):
    execution_mode: Literal["conversation", "api"] = "conversation"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    vision_model: str = ""
    image_model: str = ""


@app.get("/api/settings")
def settings():
    with LOCK:
        return {**{k: v for k, v in SETTINGS.items() if k != "api_key"}, "has_key": bool(SETTINGS["api_key"])}


@app.post("/api/settings")
def set_settings(body: SettingsInput):
    if not re.match(r"^https?://[^/]+", body.base_url) or any(c.isspace() for c in body.base_url):
        raise HTTPException(400, "请输入有效的 http(s) API 地址")
    with LOCK:
        SETTINGS.update(execution_mode=body.execution_mode, base_url=body.base_url.rstrip("/"),
                        vision_model=body.vision_model.strip(), image_model=body.image_model.strip())
        if body.api_key.strip():
            SETTINGS["api_key"] = body.api_key.strip()
    return {"ok": True}


@app.get("/api/projects")
def projects():
    return [{"id": j["id"], "name": j["name"], "characters": len(j.get("characters", []))}
            for path in sorted(DATA.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if (j := json.loads(path.read_text()))]


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        raise HTTPException(400, "支持 MP4、MOV、WebM、MKV、M4V 视频")
    jid = uuid.uuid4().hex
    folder = DATA / jid
    folder.mkdir()
    size = 0
    try:
        with (folder / ("source" + suffix)).open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 1024 ** 3:
                    raise HTTPException(413, "视频请控制在 1 GB 以内")
                target.write(chunk)
        if not size:
            raise HTTPException(400, "视频文件为空")
    except Exception:
        shutil.rmtree(folder)
        raise
    finally:
        await file.close()
    job = {"id": jid, "name": Path(file.filename).name, "video_file": "source" + suffix, "size": size,
           "video_url": f"/media/{jid}/source{suffix}", "status": "extracting", "progress": 0,
           "message": "正在读取视频", "characters": [], "frames": [], "error": None}
    with LOCK:
        JOBS[jid] = job
        save(job)
    POOL.submit(extract, job)
    return {"id": jid}


@app.get("/api/projects/{jid}")
def project(jid: str):
    return get_job(jid)


@app.post("/api/projects/{jid}/analyze")
def start_analyze(jid: str):
    job = get_job(jid)
    use_conversation = SETTINGS["execution_mode"] == "conversation"
    cfg = None if use_conversation else config("vision")
    with LOCK:
        if job["status"] not in ("frames_ready", "ready", "awaiting_analysis") or not job["frames"]:
            raise HTTPException(409, "请等待当前任务完成")
        if any(c.get("assets") for c in job["characters"]):
            raise HTTPException(409, "此项目已有角色资产；请重新上传视频建立新项目，保留现有成果。")
        if not use_conversation:
            job.pop("pending_request", None)
            job.update(status="analyzing", message="正在识别跨镜头角色与服装特征", progress=0, error=None)
            save(job)
    if use_conversation:
        return request_conversation(job, "analyze")
    POOL.submit(analyze, job, cfg)
    return {"ok": True}


class GenerateInput(BaseModel):
    character_ids: list[str] = Field(min_length=1)
    kinds: list[str] = Field(min_length=1, max_length=5)


@app.post("/api/projects/{jid}/generate")
def start_generate(jid: str, body: GenerateInput):
    job = get_job(jid)
    use_conversation = SETTINGS["execution_mode"] == "conversation"
    cfg = None if use_conversation else config("image")
    if not set(body.character_ids) <= {c["id"] for c in job["characters"]} or not set(body.kinds) <= set(KINDS):
        raise HTTPException(400, "角色或资产类型无效")
    with LOCK:
        if job["status"] not in ("ready", "awaiting_generation"):
            raise HTTPException(409, "请等待当前任务完成")
        if not use_conversation:
            job.pop("pending_request", None)
            job.update(status="generating", message="正在准备人物参考图", progress=0, error=None,
                       requested_scope={"character_ids": body.character_ids, "kinds": body.kinds})
            save(job)
    if use_conversation:
        return request_conversation(job, "generate", body.character_ids, body.kinds)
    POOL.submit(generate, job, list(dict.fromkeys(body.character_ids)), list(dict.fromkeys(body.kinds)), cfg)
    return {"ok": True}


@app.get("/api/projects/{jid}/download")
def download(jid: str):
    job = get_job(jid)
    if job["status"] in ("extracting", "analyzing", "generating"):
        raise HTTPException(409, "请等待任务完成后导出")
    folder = DATA / jid
    build_dashboard(job)
    target = folder / "character-assets.zip"
    with LOCK, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(folder / "dashboard.html", "展示大屏.html")
        manifest = {"name": job["name"], "metadata": job.get("metadata"), "characters": job["characters"],
                    "analysis": job.get("analysis"), "sampling": job.get("sampling"), "frames": job["frames"],
                    "revision": job.get("revision"), "validation": job.get("validation"),
                    "note": "AI生成图片中的未展示部分属于推测补全；人物一致性及设计细节请人工复核。"}
        archive.writestr("角色设定.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for character in job["characters"]:
            urls = [("reference", character["reference"])] + [(kind, asset["url"]) for kind, asset in character["assets"].items()]
            for kind, url in urls:
                path = folder / Path(url).name
                archive.write(path, f"character-{character['id']}/{kind}{path.suffix}")
            for n, ref in enumerate(character.get("reference_images", [])[1:], 1):
                archive.write(folder / Path(ref["url"]).name, f"character-{character['id']}/reference-{n:02d}.png")
    return FileResponse(target, filename="人物资产包.zip")


@app.get("/api/projects/{jid}/dashboard")
def dashboard(jid: str):
    job = get_job(jid)
    if job["status"] in ("extracting", "analyzing", "generating"):
        raise HTTPException(409, "请等待当前任务完成后查看大屏")
    return FileResponse(build_dashboard(job), media_type="text/html")


@app.get("/api/demo")
def demo():
    folder = ROOT / "output" / "角色资产包-01和04"
    people = []
    for cid in ("01", "04"):
        path = folder / f"character-{cid}" / "character.json"
        if not path.exists():
            continue
        person = json.loads(path.read_text())
        ref = next(a["path"] for a in person["generated_assets"] if "cutout" in a["id"])
        view = next(a["path"] for a in person["generated_assets"] if "turnaround" in a["id"])
        people.append({"id": cid, "name": person["name"], "description": person["description"],
                       "reference": "/examples/" + ref,
                       "assets": {"views": {"url": "/examples/" + view, "label": "正侧背三视图", "generated": True}}})
    return {"id": "demo", "name": "古装短剧 · 人物资产样片", "status": "ready", "message": "本地样片", "progress": 100,
            "characters": people, "frames": [], "demo": True,
            "metadata": {"width": 624, "height": 1098, "duration": 75.64, "has_audio": False}}


@app.get("/media/{jid}/{filename}")
def asset(jid: str, filename: str):
    get_job(jid)
    if not re.fullmatch(r"(?:dashboard\.html|source\.(?:mp4|mov|webm|mkv|m4v)|frame-\d+\.jpg|character-\d+(?:-ref-\d+)?\.png|\d+-(?:expressions|half|full|views|sheet)\.png)", filename):
        raise HTTPException(404)
    path = DATA / jid / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


# 只公开现有样片的图片，不公开工作区或配置文件。
@app.get("/examples/{path:path}")
def example(path: str):
    base = (ROOT / "output" / "角色资产包-01和04").resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base) or target.suffix not in (".png", ".jpg") or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
