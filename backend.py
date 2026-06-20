#!/usr/bin/env python3
"""星期五Studio 后端API服务器 — 提供通义万相图生/视频生成"""
import os, sys, json, time, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# === 配置 ===
PORT = 8800
FRONTEND_DIR = "/private/tmp/friday-studio-web"

def get_dashscope_key():
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        env_path = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("DASHSCOPE_API_KEY"):
                        key = line.strip().split("=", 1)[1].strip('"').strip("'")
                        break
    return key

DASHSCOPE_KEY = get_dashscope_key()

def call_dashscope(payload, endpoint):
    """调用 DashScope API（异步提交+轮询）"""
    url = f"https://dashscope.aliyuncs.com/api/v1/services/aigc/{endpoint}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DASHSCOPE_KEY}")
    req.add_header("X-DashScope-Async", "enable")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"API提交失败: {e.code}", "detail": e.read().decode()[:300]}
    except Exception as e:
        return {"error": f"请求异常: {str(e)}"}
    if "output" not in result or "task_id" not in result.get("output", {}):
        return {"error": f"返回异常: {json.dumps(result, ensure_ascii=False)[:300]}"}
    task_id = result["output"]["task_id"]
    query_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    max_polls = 60 if "image" in endpoint else 200
    for i in range(max_polls):
        time.sleep(3)
        qreq = urllib.request.Request(query_url)
        qreq.add_header("Authorization", f"Bearer {DASHSCOPE_KEY}")
        try:
            qresp = urllib.request.urlopen(qreq, timeout=15)
            data = json.loads(qresp.read())
            status = data["output"]["task_status"]
            if status == "SUCCEEDED":
                results = data["output"].get("results", [])
                urls = [r.get("url", "") for r in results if r.get("url")]
                return {"status": "success", "task_id": task_id, "urls": urls, "time_sec": i * 3}
            elif status == "FAILED":
                return {"error": "生成失败", "detail": data.get("output", {}).get("message", "")}
        except Exception as e:
            return {"error": f"查询异常: {str(e)}"}
    return {"error": "超时", "task_id": task_id}

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/generate-image":
            self._handle_generate_image()
        elif parsed.path == "/api/generate-video":
            self._handle_generate_video()
        else:
            self._json_response({"error": "未知接口"}, 404)

    def _handle_generate_image(self):
        if not DASHSCOPE_KEY:
            self._json_response({"error": "DASHSCOPE_API_KEY 未配置"}, 500)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            prompt = body.get("prompt", "")
            size = body.get("size", "1024*1024")
            if not prompt:
                self._json_response({"error": "prompt 不能为空"}, 400)
                return
        except Exception as e:
            self._json_response({"error": f"参数解析失败: {str(e)}"}, 400)
            return

        payload = {
            "model": "wanx-v1",
            "input": {"prompt": prompt},
            "parameters": {"size": size, "n": 1}
        }
        result = call_dashscope(payload, "text2image/image-synthesis")
        self._json_response(result)

    def _handle_generate_video(self):
        if not DASHSCOPE_KEY:
            self._json_response({"error": "DASHSCOPE_API_KEY 未配置"}, 500)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            prompt = body.get("prompt", "")
            image_url = body.get("image_url", None)
            duration = body.get("duration", 5)
            if not prompt:
                self._json_response({"error": "prompt 不能为空"}, 400)
                return
        except Exception as e:
            self._json_response({"error": f"参数解析失败: {str(e)}"}, 400)
            return

        payload = {
            "model": "wanx2.1-t2v-turbo",
            "input": {"prompt": prompt},
            "parameters": {"duration": duration}
        }
        if image_url:
            payload["input"]["img_url"] = image_url
        result = call_dashscope(payload, "video-generation/video-synthesis")
        self._json_response(result)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_GET(self):
        # Health check
        if self.path == "/api/health":
            self._json_response({"status": "ok", "dashscope": bool(DASHSCOPE_KEY)})
            return
        # Serve frontend static files
        path = self.path
        if path == "/" or path == "":
            path = "/index.html"
        file_path = FRONTEND_DIR + path
        if not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        ext = os.path.splitext(file_path)[1]
        mime_map = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }
        mime = mime_map.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

if __name__ == "__main__":
    print(f"🚀 星期五Studio 后端启动")
    print(f"   📡 服务地址: http://localhost:{PORT}")
    print(f"   🖼️  DashScope: {'✅ 已配置' if DASHSCOPE_KEY else '❌ 未配置'}")
    print(f"   📂 前端文件: {FRONTEND_DIR}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务关闭")
        server.server_close()
