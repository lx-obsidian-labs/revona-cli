export interface Env { NVIDIA_NIM_API_KEY: string; REVONA_CLIENT_TOKEN: string; NVIDIA_NIM_MODEL?: string }
const upstream = "https://integrate.api.nvidia.com/v1/chat/completions";
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") return Response.json({ ok: true, service: "revona-nim" });
    if (url.pathname !== "/v1/chat/completions") return new Response("Not found", { status: 404 });
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    const token = request.headers.get("authorization");
    if (!env.REVONA_CLIENT_TOKEN || !env.NVIDIA_NIM_API_KEY || token !== `Bearer ${env.REVONA_CLIENT_TOKEN}`) return new Response("Unauthorized", { status: 401 });
    const length = Number(request.headers.get("content-length") || "0");
    if (length > 100_000) return new Response("Request too large", { status: 413 });
    let body: unknown;
    try { const raw = await request.text(); if (raw.length > 100_000) return new Response("Request too large", { status: 413 }); body = JSON.parse(raw); } catch { return new Response("Invalid JSON", { status: 400 }); }
    if (!body || typeof body !== "object" || !Array.isArray((body as { messages?: unknown }).messages)) return new Response("Invalid messages", { status: 400 });
    const input = body as { messages: unknown[]; stream?: boolean; temperature?: number; max_tokens?: number };
    if (input.messages.length > 40 || input.stream === true) return new Response("Unsupported request", { status: 400 });
    const messages = input.messages.map((message) => {
      if (!message || typeof message !== "object") return null;
      const m = message as { role?: string; content?: unknown };
      return ["system", "user", "assistant"].includes(m.role ?? "") && typeof m.content === "string" && m.content.length <= 16000 ? { role: m.role, content: m.content } : null;
    });
    if (messages.some((message) => !message)) return new Response("Invalid message format", { status: 400 });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch(upstream, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${env.NVIDIA_NIM_API_KEY}` },
        body: JSON.stringify({
          model: env.NVIDIA_NIM_MODEL || "meta/llama-3.1-8b-instruct",
          messages, stream: false,
          temperature: typeof input.temperature === "number" ? Math.max(0, Math.min(1, input.temperature)) : 0.4,
          max_tokens: typeof input.max_tokens === "number" ? Math.max(1, Math.min(2048, input.max_tokens)) : 768,
        }),
        signal: controller.signal,
      });
      if (!response.ok) return Response.json({ error: "NIM request failed", status: response.status }, { status: response.status === 429 ? 429 : 502 });
      return new Response(response.body, { status: 200, headers: { "content-type": "application/json", "cache-control": "no-store" } });
    } catch { return Response.json({ error: "NIM unavailable" }, { status: 504 }); }
    finally { clearTimeout(timeout); }
  },
};
