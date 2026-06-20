#!/usr/bin/env python3
"""星期五Studio 后端API — Flask版，部署到PythonAnywhere"""
import os, sys, json, time, urllib.request, urllib.error, re
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# ====== 配置 ======
ATLAS_KEY = os.environ.get("ATLAS_KEY", "")
ATLAS_BASE = "https://api.atlascloud.ai/v1"

# ====== LLM：写剧本 ======
@app.route("/api/generate-script", methods=["POST"])
def generate_script():
    data = request.get_json(force=True)
    idea = data.get("idea", "")
    style = data.get("style", "写实电影")
    if not idea:
        return jsonify({"error": "idea required"}), 400

    prompt = f"""你是一个专业的视频编剧。根据以下创意，写一个5场的漫剧剧本（每场包含场景描述、角色动作、对话）：
创意：{idea}
风格：{style}
输出格式：
Scene 1 — [场景名]
[描述]

Scene 2 — [场景名]
[描述]
...共5场"""

    result = call_atlas_llm(prompt)
    return jsonify(result)

# ====== 生成图片 ======
@app.route("/api/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json(force=True)
    prompt_text = data.get("prompt", "")
    if not prompt_text:
        return jsonify({"error": "prompt required"}), 400

    try:
        body = json.dumps({
            "model": "google/gemini-2.5-flash-image",
            "messages": [{"role": "user", "content": prompt_text}]
        }).encode()
        req = urllib.request.Request(
            ATLAS_BASE + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + ATLAS_KEY,
                "Content-Type": "application/json"
            }
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())

        if data.get("choices") and data["choices"][0].get("message"):
            content = data["choices"][0]["message"].get("content", "")
            # Try to extract image URL from the response
            url_match = re.search(r'!\[.*?\]\((.*?)\)', content)
            if url_match:
                return jsonify({"status": "success", "urls": [url_match.group(1)]})
            url_match = re.search(r'https?://[^\s)\]]+\.(?:png|jpg|jpeg|webp)', content, re.I)
            if url_match:
                return jsonify({"status": "success", "urls": [url_match.group(0)]})
            # Return the text content if no URL found
            return jsonify({"status": "text", "content": content[:500]})

        return jsonify({"error": "生成失败", "detail": str(data)[:300]}), 500
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"HTTP {e.code}", "detail": e.read().decode()[:200]}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500

# ====== 健康检查 ======
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": time.time()})

# ====== Atlas Cloud LLM ======
def call_atlas_llm(prompt):
    body = json.dumps({
        "model": "deepseek-ai/deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.8
    }).encode()
    req = urllib.request.Request(
        ATLAS_BASE + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + ATLAS_KEY,
            "Content-Type": "application/json"
        }
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        if data.get("choices") and data["choices"][0]:
            return {"status": "success", "content": data["choices"][0]["message"]["content"]}
        return {"error": "LLM调用失败", "detail": data}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=False)
