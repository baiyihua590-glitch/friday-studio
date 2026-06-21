const ATLAS_KEY = "apikey-1febaee01bc844018c0ce2c102a0b99e";

function corsOk() {
  return {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
    }
  };
}

async function callAtlasLLM(prompt) {
  const resp = await fetch("https://api.atlascloud.ai/v1/chat/completions", {
    headers: {"Authorization": "Bearer " + ATLAS_KEY, "Content-Type": "application/json"},
    method: "POST",
    body: JSON.stringify({
      model: "deepseek-ai/deepseek-v4-flash",
      messages: [{role: "user", content: prompt}],
      max_tokens: 4096
    })
  });
  const data = await resp.json();
  return {status: "success", content: data.choices?.[0]?.message?.content || "生成失败"};
}

async function submitImage(model, prompt, size) {
  const body = JSON.stringify(
    model.includes("flux")
      ? {model, input: {prompt, size, num_images: 1, seed: -1}}
      : {model, prompt, size, quality: "medium", output_format: "jpeg"}
  );
  const resp = await fetch("https://api.atlascloud.ai/api/v1/model/generateImage", {
    headers: {"Authorization": "Bearer " + ATLAS_KEY, "Content-Type": "application/json"},
    method: "POST", body
  });
  return await resp.json();
}

async function pollPrediction(url) {
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const r = await fetch(url, {headers: {"Authorization": "Bearer " + ATLAS_KEY}});
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
  if (event.httpMethod !== "POST") return {statusCode: 405, ...corsOk(), body: JSON.stringify({error: "POST only"})};
  
  const {action, prompt, images, imageUrl} = JSON.parse(event.body || "{}");
  
  try {
    if (action === "script" || action === "storyboard") {
      const r = await callAtlasLLM(prompt);
      return {statusCode: 200, ...corsOk(), body: JSON.stringify(r)};
    }
    if (action === "image") {
      const d = await submitImage("black-forest-labs/flux-schnell", prompt, "1024x1024");
      if (d.data?.id) {
        const pollUrl = d.data.urls?.get || "https://api.atlascloud.ai/api/v1/model/prediction/" + d.data.id;
        const url = await pollPrediction(pollUrl);
        return {statusCode: 200, ...corsOk(), body: JSON.stringify({status: url ? "success" : "error", url, urls: url ? [url] : []})};
      }
      return {statusCode: 200, ...corsOk(), body: JSON.stringify({error: "提交失败", detail: d})};
    }
    if (action === "proxy" && imageUrl) {
      const r = await fetch(imageUrl);
      const body = await r.arrayBuffer();
      return {
        statusCode: r.status,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Content-Type": r.headers.get("Content-Type") || "image/jpeg"
        },
        body: Buffer.from(body).toString("base64"),
        isBase64Encoded: true
      };
    }
    return {statusCode: 400, ...corsOk(), body: JSON.stringify({error: "未知action"})};
  } catch(e) {
    return {statusCode: 500, ...corsOk(), body: JSON.stringify({error: e.message})};
  }
};
