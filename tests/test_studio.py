"""真实 FFmpeg 解码 + 模拟模型服务验证，不消耗 API 额度。"""
import base64
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
import httpx
from PIL import Image
import server


class StudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        cls.clip = Path(cls.work.name) / "clip.mp4"
        subprocess.run([server.imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error",
                        "-f", "lavfi", "-i", "color=c=gray:s=96x128:d=1", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(cls.clip)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_patch = patch.object(server, "DATA", Path(self.temp.name))
        self.data_patch.start()
        self.jobs_patch = patch.object(server, "JOBS", {})
        self.jobs_patch.start()
        self.settings_patch = patch.dict(server.SETTINGS, {
            "base_url": "https://mock.invalid/v1", "api_key": "test-secret",
            "vision_model": "vision-test", "image_model": "image-test", "execution_mode": "api"})
        self.settings_patch.start()
        self.client = TestClient(server.app)
        # 同步执行后台任务，便于稳定检查结果。
        self.pool_patch = patch.object(server.POOL, "submit", side_effect=lambda f, *a: f(*a))
        self.pool_patch.start()

    def tearDown(self):
        self.client.close()
        self.pool_patch.stop()
        self.settings_patch.stop()
        self.jobs_patch.stop()
        self.data_patch.stop()
        self.temp.cleanup()

    def upload(self):
        with self.clip.open("rb") as video:
            response = self.client.post("/api/upload", files={"file": ("测试片.mp4", video, "video/mp4")})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def model_client(self, handler):
        original = httpx.Client
        return patch.object(server.httpx, "Client", side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw))

    def character_response(self, bbox=None):
        return {"characters": [{"name": '角色 "甲"', "description": "黑发灰衣的角色",
                                "frame_index": 0, "bbox": bbox or [0, 0, 1, 1]}]}

    def analyze(self, jid):
        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "vision-test")
            content = payload["messages"][0]["content"]
            self.assertEqual(sum(c["type"] == "image_url" for c in content), 6)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(self.character_response())}}]})
        with self.model_client(handler):
            self.assertEqual(self.client.post(f"/api/projects/{jid}/analyze").status_code, 200)
        self.assertEqual(server.get_job(jid)["status"], "ready")

    def test_decode_analyze_generate_export(self):
        jid = self.upload()
        job = server.get_job(jid)
        self.assertEqual(job["status"], "frames_ready")
        self.assertFalse(job["metadata"]["has_audio"])
        self.assertEqual((job["metadata"]["width"], job["metadata"]["height"]), (96, 128))
        self.assertEqual(len(job["frames"]), 6)
        with Image.open(server.DATA / jid / Path(job["frames"][0]["url"]).name) as frame:
            self.assertEqual(frame.size, (96, 128))
        self.analyze(jid)
        picture = io.BytesIO()
        Image.new("RGB", (64, 64), "gray").save(picture, format="PNG")
        calls = []

        def handler(request):
            self.assertTrue(request.url.path.endswith("/images/edits"))
            self.assertIn(b'name="image"', request.content)
            self.assertIn(b'character-01.png', request.content)
            self.assertIn(b'Preserve the EXACT same', request.content)
            calls.append(request)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(picture.getvalue()).decode()}]})

        with self.model_client(handler):
            response = self.client.post(f"/api/projects/{jid}/generate", json={"character_ids": ["01"], "kinds": list(server.KINDS)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 5)
        self.assertEqual(len(job["characters"][0]["assets"]), 5)
        self.assertEqual(job["status"], "ready")
        self.assertEqual(self.client.post(f"/api/projects/{jid}/analyze").status_code, 409)
        response = self.client.get(f"/api/projects/{jid}/download")
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(len(archive.namelist()), 8)
            self.assertIn("展示大屏.html", archive.namelist())
            self.assertTrue(all(not n.endswith(".mp4") for n in archive.namelist()))
            self.assertEqual(set(json.loads(archive.read("角色设定.json"))["characters"][0]["assets"]), set(server.KINDS))
        self.assertNotIn("test-secret", (server.DATA / jid / "project.json").read_text())
        for asset in job["characters"][0]["assets"].values():
            self.assertEqual(self.client.get(asset["url"]).status_code, 200)

    def test_invalid_upload_and_corrupt_video(self):
        self.assertEqual(self.client.post("/api/upload", files={"file": ("a.txt", b"hi")}).status_code, 400)
        self.assertEqual(self.client.post("/api/upload", files={"file": ("a.mp4", b"")}).status_code, 400)
        response = self.client.post("/api/upload", files={"file": ("a.mp4", b"not a video")})
        self.assertEqual(server.get_job(response.json()["id"])["status"], "error")

    def test_invalid_model_crop_is_retryable(self):
        jid = self.upload()
        def handler(request):
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(self.character_response([-1, 0, 1, 1]))}}]})
        with self.model_client(handler):
            self.client.post(f"/api/projects/{jid}/analyze")
        job = server.get_job(jid)
        self.assertEqual(job["status"], "frames_ready")
        self.assertTrue(job["error"])
        self.assertEqual(job["characters"], [])

    def test_model_error_preserves_project(self):
        jid = self.upload()
        self.analyze(jid)
        with self.model_client(lambda request: httpx.Response(429, json={"error": "quota"})):
            self.client.post(f"/api/projects/{jid}/generate", json={"character_ids": ["01"], "kinds": ["expressions"]})
        job = server.get_job(jid)
        self.assertEqual(job["status"], "ready")
        self.assertIn("HTTP 429", job["error"])
        self.assertEqual(job["characters"][0]["assets"], {})

    def test_settings_key_and_local_access(self):
        response = self.client.get("/api/settings")
        self.assertTrue(response.json()["has_key"])
        self.assertNotIn("test-secret", response.text)
        response = self.client.post("/api/settings", json={"base_url": "https://mock.invalid/v1", "api_key": "", "vision_model": "v", "image_model": "i"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(server.SETTINGS["api_key"], "test-secret")
        self.assertEqual(self.client.post("/api/settings", headers={"origin": "https://elsewhere.invalid"}, json={"base_url": "https://mock.invalid"}).status_code, 403)
        self.assertEqual(self.client.get("/media/invalid/project.json").status_code, 404)
        self.assertEqual(self.client.get("/examples/character-01/character.json").status_code, 404)
        self.assertEqual(self.client.post("/api/settings", json={"base_url": "file:///etc/passwd"}).status_code, 400)

    def test_missing_model_prevents_task(self):
        jid = self.upload()
        with patch.dict(server.SETTINGS, {"api_key": ""}):
            self.assertEqual(self.client.post(f"/api/projects/{jid}/analyze").status_code, 400)
        self.assertEqual(server.get_job(jid)["status"], "frames_ready")

    def test_current_conversation_queues_without_key_or_network(self):
        jid = self.upload()
        with patch.dict(server.SETTINGS, {"execution_mode": "conversation", "api_key": "", "vision_model": ""}), \
                patch.object(server.httpx, "Client", side_effect=AssertionError("不应调用模型 API")):
            response = self.client.post(f"/api/projects/{jid}/analyze")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["engine"], "current-conversation")
        self.assertIn("$drama-assets", response.json()["prompt"])
        self.assertEqual(server.get_job(jid)["status"], "awaiting_analysis")

    def test_skill_defaults_all_roles_and_all_assets(self):
        from scripts.drama_assets import plan, register_asset, finalize
        jid = self.upload()
        job = server.get_job(jid)
        people = [dict(self.character_response()["characters"][0], name=f"角色{i}") for i in range(10)]
        server.apply_characters(job, people, coverage_note="测试样本")
        self.assertEqual(len(plan(job)), 50)
        self.assertEqual(job["analysis"]["engine"], "current-conversation")
        with self.assertRaisesRegex(ValueError, "尚未完成"):
            finalize(job)
        image = server.DATA / jid / "test-picture.png"
        Image.new("RGB", (256, 256), "gray").save(image)
        register_asset(job, "01", "half", image)
        self.assertEqual(len(plan(job)), 49)
        with self.assertRaisesRegex(ValueError, "已存在"):
            register_asset(job, "01", "half", image)
        result = finalize(job, allow_incomplete=True)
        self.assertFalse(result["complete"])
        html = Path(result["dashboard"]).read_text()
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("角色9", html)
        self.assertIn("尚未生成", html)
        self.assertNotIn("{{", html)
        self.assertNotIn('src="http', html)
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertIn("展示大屏.html", archive.namelist())
            self.assertEqual(json.loads(archive.read("角色设定.json"))["analysis"]["coverage_note"], "测试样本")

    def test_web_receives_external_skill_results(self):
        jid = self.upload()
        self.client.get(f"/api/projects/{jid}")
        path = server.DATA / jid / "project.json"
        data = json.loads(path.read_text())
        data["message"] = "当前对话写入的新分析"
        path.write_text(json.dumps(data))
        self.assertEqual(self.client.get(f"/api/projects/{jid}").json()["message"], data["message"])

    def test_skill_dense_sampling_has_actual_timestamps(self):
        from scripts.drama_assets import prepare
        with patch.object(server.httpx, "Client", side_effect=AssertionError("不应调用模型 API")):
            result = prepare(video=self.clip, interval=0.2)
        job = server.get_job(result["id"])
        self.assertGreaterEqual(result["frame_count"], 4)
        self.assertTrue(all(Path(p).is_file() for p in result["contact_sheets"]))
        self.assertEqual(job["sampling"]["timestamps"], "decoded-pts")
        self.assertEqual(job["requested_scope"]["characters"], "all")
        self.assertEqual(set(job["requested_scope"]["kinds"]), set(server.KINDS))
        self.assertEqual(job["frames"][0]["seconds"], 0)

    def test_conversation_generation_has_no_api_requirement(self):
        from scripts.drama_assets import register_asset, plan
        jid = self.upload()
        job = server.get_job(jid)
        server.apply_characters(job, self.character_response()["characters"])
        with patch.dict(server.SETTINGS, {"execution_mode": "conversation", "api_key": ""}):
            response = self.client.post(f"/api/projects/{jid}/generate", json={"character_ids": ["01"], "kinds": ["half"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["kind"] for item in plan(job)], ["half"])
        image = server.DATA / jid / "test-picture.png"
        Image.new("RGB", (256, 256), "gray").save(image)
        register_asset(job, "01", "half", image)
        self.assertEqual(job["status"], "ready")
        self.assertNotIn("pending_request", job)
        self.assertEqual(plan(job), [])

    def test_complete_skill_export_validates_every_asset(self):
        from scripts.drama_assets import register_asset, finalize
        jid = self.upload()
        job = server.get_job(jid)
        server.apply_characters(job, self.character_response()["characters"])
        image = server.DATA / jid / "test-picture.png"
        Image.new("RGB", (256, 256), "gray").save(image)
        for kind in server.KINDS:
            register_asset(job, "01", kind, image)
        result = finalize(job)
        self.assertTrue(result["complete"])
        self.assertEqual(result["missing"], [])
        self.assertIn("全部资产已就绪", Path(result["dashboard"]).read_text())
        self.assertEqual(self.client.get(f"/api/projects/{jid}/dashboard").status_code, 200)

    def test_multiple_original_references_reach_image_service_and_zip(self):
        jid = self.upload()
        job = server.get_job(jid)
        person = self.character_response()["characters"][0]
        person["references"] = [{"frame_index": 0, "bbox": [0, 0, 1, 1], "role": "identity"},
                                {"frame_index": 1, "bbox": [0.1, 0.1, 0.9, 0.9], "role": "outfit"}]
        server.apply_characters(job, [person])
        job["characters"][0]["identity_review"] = {"status": "accepted", "note": "旧基准审核"}
        image = io.BytesIO()
        Image.new("RGB", (256, 256), "gray").save(image, format="PNG")
        calls = []
        def handler(request):
            self.assertEqual(request.content.count(b'name="image[]"'), 2)
            self.assertIn(b'character-01.png', request.content)
            self.assertIn(b'character-01-ref-01.png', request.content)
            calls.append(request)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(image.getvalue()).decode()}]})
        with self.model_client(handler):
            self.client.post(f"/api/projects/{jid}/generate", json={"character_ids": ["01"], "kinds": ["half"]})
        self.assertEqual(len(calls), 1)
        self.assertEqual(job["characters"][0]["identity_review"]["status"], "pending")
        self.assertEqual(len(job["characters"][0]["assets"]["half"]["reference_images"]), 2)
        self.assertEqual(self.client.get(job["characters"][0]["reference_images"][1]["url"]).status_code, 200)
        with zipfile.ZipFile(io.BytesIO(self.client.get(f"/api/projects/{jid}/download").content)) as z:
            self.assertIn("character-01/reference-01.png", z.namelist())

    def test_identity_gate_rejects_drift_and_invalidates_replaced_baseline(self):
        from scripts.drama_assets import plan, register_asset, review_identity, finalize
        jid = self.upload()
        job = server.get_job(jid)
        server.apply_characters(job, self.character_response()["characters"])
        server.update(job, require_identity_review=True)
        self.assertEqual([t["kind"] for t in plan(job)], ["half"])
        path = server.DATA / jid / "baseline.png"
        Image.new("RGB", (256, 256), "gray").save(path)
        register_asset(job, "01", "half", path)
        self.assertEqual(plan(job), [])
        with self.assertRaisesRegex(ValueError, "相似度"):
            finalize(job)
        review_identity(job, "01", False, "与原片不符：多出了发髻")
        self.assertEqual([t["kind"] for t in plan(job)], ["half"])
        review_identity(job, "01", True, "对照两张原帧，发际线、眼型和衣领一致")
        self.assertEqual(len(plan(job)), 4)
        self.assertEqual(len(job["characters"][0]["identity_review"]["baseline_sha256"]), 64)
        register_asset(job, "01", "half", path, replace=True)
        self.assertEqual(job["characters"][0]["identity_review"]["status"], "pending")

    def test_bad_secondary_reference_does_not_write_partial_crop(self):
        jid = self.upload()
        job = server.get_job(jid)
        person = self.character_response()["characters"][0]
        person["references"] = [{"frame_index": 0, "bbox": [0, 0, 1, 1]},
                                {"frame_index": 1, "bbox": [-1, 0, 1, 1]}]
        with self.assertRaises(ValueError):
            server.apply_characters(job, [person])
        self.assertFalse((server.DATA / jid / "character-01.png").exists())


if __name__ == "__main__":
    unittest.main()
