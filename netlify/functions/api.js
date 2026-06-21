const ATLAS_KEY = "apikey-1febaee01bc844018c0ce2c102a0b99e";
const ATLAS = "https://api.atlascloud.ai";
const HEADERS = {"Authorization": "Bearer " + ATLAS_KEY, "Content-Type": "application/json"};

function corsOk() {
  return {headers: {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "POST, GET, OPTIONS"}};
}

async function submitJob(endpoint, body) {
  const r = await fetch(ATLAS + endpoint, {method: "POST", headers: HEADERS, body: JSON.stringify(body)});
  return await r.json();
}

async function poll(url) {
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const r = await fetch(url, {headers: HEADERS});
    const d = await r.json();
    if (d.data?.status === "completed") {
      const out = d.data.outputs;
      return Array.isArray(out) ? out[0] : (out?.url || out);
    }
    if (d.data?.status === "failed") return null;
  }
  return null;
}

exports.handler = async (event, context) => {
  if (event.httpMethod === "OPTIONS") return {statusCode: 200, ...corsOk(), body: ""};
  if (event.httpMethod === "GET") {
    const params = new URLSearchParams(event.queryStringParameters);
    const imageUrl = params.get("imageUrl");
    if (imageUrl) {
      try {
        const r = await fetch(decodeURIComponent(imageUrl));
        const body = await r.arrayBuffer();
        return {statusCode: r.status, headers: {"Access-Control-Allow-Origin": "*", "Content-Type": r.headers.get("Content-Type") || "image/jpeg"}, body: Buffer.from(body).toString("base64"), isBase64Encoded: true};
      } catch(e) {
        return {statusCode: 500, ...corsOk(), body: JSON.stringify({error: e.message})};
      }
    }
    return {statusCode: 200, ...corsOk(), body: "OK"};
  }
  
  try {
    const data = JSON.parse(event.body || "{}");
    const {action, prompt, images, size, duration} = data;
    
    if (action === "script") {
      const r = await submitJob("/v1/chat/completions", {
        model: "google/gemini-2.5-flash-lite",
        messages: [{role: "user", content: "用50-100字写一段3-5场的短视频剧本（每场只写一句话）。主题：" + prompt + "。风格：" + (data.style || "") + "。氛围：" + (data.atmosphere || "")}], max_tokens: 512
      });
      return {statusCode: 200, ...corsOk(), body: JSON.stringify({status: "success", content: r.choices?.[0]?.message?.content || "生成失败"})};
    }
    
    if (action === "storyboard") {
      const sp = "生成3-5个分镜的JSON数组（scene_num,location,action,camera_angle,camera_motion）。剧本：" + prompt;
      const r = await submitJob("/v1/chat/completions", {
        model: "google/gemini-2.5-flash-lite",
        messages: [{role: "user", content: sp}], max_tokens: 1024
      });
      return {statusCode: 200, ...corsOk(), body: JSON.stringify({status: "success", content: r.choices?.[0]?.message?.content || "生成失败"})};
    }
    
    if (action === "frames") {
      const scene = prompt;
      const charDesc2 = data.character || "";
      const style2 = data.style || "温馨";
      const prompts = [
        "首帧画面——" + scene + "，角色：" + charDesc2 + "，风格：" + style2,
        "尾帧画面——" + scene + "（不同角度或动作），角色：" + charDesc2 + "，风格：" + style2
      ];
      const results = await Promise.all(prompts.map(async (p) => {
        const body = JSON.stringify({model: "black-forest-labs/flux-schnell", input: {prompt: p, size: "1024x1024", num_images: 1, seed: -1}});
        const d = await submitJob("/api/v1/model/generateImage", JSON.parse(body));
        if (d.data?.id) {
          const pollUrl = d.data.urls?.get || "https://api.atlascloud.ai/api/v1/model/prediction/" + d.data.id;
          const url = await poll(pollUrl);
          return {name: p.includes("首帧") ? "首帧" : "尾帧", url};
        }
        return {name: "", url: null};
      }));
      return {statusCode: 200, ...corsOk(), body: JSON.stringify({status: "success", frames: results})};
    }
    
    if (action === "image") {
      const body = JSON.stringify({model: "black-forest-labs/flux-schnell", input: {prompt, size: size || "1024x1024", num_images: 1, seed: -1}});
      const d = await submitJob("/api/v1/model/generateImage", JSON.parse(body));
      const submitData = typeof d === "object" ? d : {data: {}};
      const d2 = submitData.data;
      if (d2?.id) {
        const pollUrl = d2.urls?.get || "https://api.atlascloud.ai/api/v1/model/prediction/" + d2.id;
        const url = await poll(pollUrl);
        return {statusCode: 200, ...corsOk(), body: JSON.stringify({status: url ? "success" : "error", url, urls: url ? [url] : []})};
      }
      return {statusCode: 200, ...corsOk(), body: JSON.stringify({error: "提交失败"})};
    }
    
    if (action === "video") {
      const body = JSON.stringify({model: "vidu/q3/reference-to-video", images: images || [], prompt, duration: duration || 5});
      const d = await submitJob("/api/v1/model/generateVideo", JSON.parse(body));
      const d2 = d.data;
      if (d2?.id) {
        const pollUrl = d2.urls?.get || "https://api.atlascloud.ai/api/v1/model/prediction/" + d2.id;
        return {statusCode: 200, ...corsOk(), body: JSON.stringify({status: "processing", poll_url: pollUrl})};
      }
      return {statusCode: 200, ...corsOk(), body: JSON.stringify({error: "提交失败"})};
    }
    
    if (action === "poll") {
      const url = prompt; // poll_url passed as prompt
      const r = await fetch(url, {headers: HEADERS});
      const d = await r.json();
      const status = d.data?.status || "failed";
      const out = d.data?.outputs;
      if (status === "completed" && out) {
        const u = Array.isArray(out) ? out[0] : (out?.url || out);
        return {statusCode: 200, ...corsOk(), body: JSON.stringify({status: "completed", url: u, output: out})};
      }
      return {statusCode: 200, ...corsOk(), body: JSON.stringify({status})};
    }
    
    return {statusCode: 400, ...corsOk(), body: JSON.stringify({error: "未知action: " + action})};
  } catch(e) {
    return {statusCode: 500, ...corsOk(), body: JSON.stringify({error: e.message})};
  }
};
