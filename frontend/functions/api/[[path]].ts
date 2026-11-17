/* Cloudflare Pages Function: same-origin API proxy for /api/*.
 *
 * This keeps the browser on one origin and avoids CORS/preflight issues for
 * normal JSON endpoints. The ZENJI backend still performs Supabase auth and RLS.
 *
 * Set API_ORIGIN in Cloudflare Pages (Settings → Environment variables):
 *   API_ORIGIN=https://zenji-api.example.workers.dev
 *
 * Streaming chat is proxied unchanged (SSE).
 */

export interface Env {
  API_ORIGIN?: string;
  ALLOWED_ORIGIN?: string;
}

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-encoding",
  "content-length",
]);

function allowedOrigin(request: Request, env: Env): string | null {
  const origin = request.headers.get("origin");
  if (!origin || !env.ALLOWED_ORIGIN) return null;
  return origin === env.ALLOWED_ORIGIN ? origin : null;
}

function corsHeaders(request: Request, env: Env): Headers {
  const headers = new Headers();
  const origin = allowedOrigin(request, env);
  if (origin) {
    headers.set("access-control-allow-origin", origin);
    headers.set("vary", "Origin");
  }
  headers.set("access-control-allow-methods", "GET,POST,PATCH,DELETE,OPTIONS");
  headers.set("access-control-allow-headers", "authorization, content-type, accept");
  headers.set("access-control-max-age", "86400");
  return headers;
}

export async function onRequest(context: {
  request: Request;
  env: Env;
}): Promise<Response> {
  const { request, env } = context;
  const url = new URL(request.url);
  const base = (env.API_ORIGIN || "").trim().replace(/\/$/, "");
  const cors = corsHeaders(request, env);

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }

  if (!base) {
    return new Response(
      JSON.stringify({
        error: {
          code: "CONFIGURATION_MISSING",
          message: "API_ORIGIN ist auf Cloudflare Pages nicht gesetzt.",
        },
      }),
      {
        status: 503,
        headers: {
          "content-type": "application/json; charset=utf-8",
          ...Object.fromEntries(cors),
        },
      },
    );
  }

  const target = `${base}${url.pathname}${url.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("cf-connecting-ip");
  headers.delete("cf-ipcountry");
  headers.delete("cf-ray");
  headers.delete("cf-visitor");
  headers.delete("cf-worker");
  headers.delete("x-forwarded-proto");
  headers.delete("x-forwarded-for");
  headers.delete("x-real-ip");
  headers.set("host", new URL(base).host);

  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    redirect: "manual",
  });

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      responseHeaders.set(key, value);
    }
  });
  cors.forEach((value, key) => {
    if (key.toLowerCase() !== "vary") responseHeaders.set(key, value);
  });
  const vary = responseHeaders.get("vary");
  if (cors.has("vary")) {
    responseHeaders.set("vary", vary ? `${vary}, Origin` : "Origin");
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}