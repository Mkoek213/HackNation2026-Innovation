import { NextRequest } from "next/server";

/**
 * Trusted browser origins for mutating requests through this BFF.
 * Same allowlist idea as backend ALLOWED_HOSTS: configure explicitly, never infer
 * from Next.js request URL construction (HOSTNAME/bind address is not the public origin).
 */
function trustedOrigins(): Set<string> {
  const origins = new Set<string>();
  const expand = (value: string) =>
    value.replaceAll("${FRONTEND_PORT}", process.env.FRONTEND_PORT?.trim() || "3000").trim();

  const hosts = process.env.ALLOWED_HOSTS?.trim();
  if (hosts?.startsWith("[")) {
    try {
      const parsed: unknown = JSON.parse(expand(hosts));
      if (Array.isArray(parsed)) for (const item of parsed) if (typeof item === "string" && item) origins.add(item);
    } catch {
      // Invalid JSON is treated as misconfiguration (empty allowlist).
    }
  } else if (hosts) {
    for (const item of expand(hosts).split(",")) if (item) origins.add(item);
  }

  const frontend = process.env.FRONTEND_BASE_URL?.trim();
  if (frontend) origins.add(expand(frontend));

  return origins;
}

function backendBase(): string {
  return process.env.BACKEND_URL?.trim() || "http://127.0.0.1:8000";
}

function assertTrustedOrigin(request: NextRequest): Response | null {
  if (request.method === "GET" || request.method === "HEAD") return null;
  const origin = request.headers.get("origin");
  const allowed = trustedOrigins();
  if (!origin || allowed.size === 0 || !allowed.has(origin)) {
    return Response.json(
      { detail: "Origin is not allowed for this proxy." },
      { status: 403 },
    );
  }
  return null;
}

// Fixed backend + path allowlist: this route must not become an open proxy.
async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const pathname = path.join("/");
  if (pathname !== "api/v1/knowledge/catalog" && !/^(auth\/(login|register|logout|session)|users\/me|operator\/(?:staff|pdf)|contact|matters(?:\/\d+(?:\/(?:thread|pdf))?)?|visits|workspace\/conversations(?:\/\d+(?:\/(?:messages|handoff(?:\/(?:send|pdf))?|artifacts\/[a-f0-9-]{36}\/pdf)|\/innovations\/[a-z0-9-]{1,120}\/open)?)?|stats\/(?:site|workspace|innovations|trends|tags(?:\/\d+|\/timeline)?|projects(?:\/\d+)?)|api\/v1\/knowledge\/(?:innovations(?:\/[a-z0-9-]+(?:\/documents\/[a-f0-9]{32})?)?|categories|taxonomy))$/.test(pathname)) {
    return new Response(null, { status: 404 });
  }
  // Knowledge writes: admin upload, card edit, and the unstored draft that fills the upload form.
  const knowledgeUpload = (request.method === "PUT" || request.method === "PATCH") && /^api\/v1\/knowledge\/innovations\/(?!draft$)[a-z0-9-]+$/.test(pathname);
  const knowledgeDraft = request.method === "POST" && pathname === "api/v1/knowledge/innovations/draft";
  const chatTurn = request.method === "POST" && /^workspace\/conversations\/\d+\/messages$/.test(pathname);
  if ((pathname.startsWith("api/v1/knowledge/") || pathname.startsWith("stats/")) && request.method !== "GET" && !knowledgeUpload && !knowledgeDraft) {
    return new Response(null, { status: 405 });
  }
  // Contact messages are listed through the backend API only; the browser can only send one.
  if ((pathname === "visits" || pathname === "contact") && request.method !== "POST") {
    return new Response(null, { status: 405 });
  }
  const originError = assertTrustedOrigin(request);
  if (originError) return originError;

  const headers = new Headers();
  const csrfHeader = (process.env.CSRF_HEADER_NAME ?? "x-csrf-token").toLowerCase();
  for (const name of ["cookie", "content-type", csrfHeader]) {
    if (request.headers.has(name)) headers.set(name, request.headers.get(name)!);
  }
  try {
    const upstream = await fetch(`${backendBase()}/${pathname}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      cache: "no-store",
      redirect: "manual",
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      // Ingestion extracts, classifies and embeds every document before answering.
      signal: AbortSignal.timeout(knowledgeUpload ? 600000 : knowledgeDraft ? 180000 : chatTurn ? 660000 : 100000),
    });
    const outgoing = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "content-disposition", "content-length", "x-content-type-options"]) {
      if (upstream.headers.has(name)) outgoing.set(name, upstream.headers.get(name)!);
    }
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append("set-cookie", cookie);
    if (pathname === "auth/login" && upstream.ok) {
      // Cookie sessions never expose a bearer token to browser code, even in 'both' mode.
      outgoing.delete("content-length");
      return Response.json({ detail: "Logged in." }, { status: upstream.status, headers: outgoing });
    }
    return new Response(upstream.body, { status: upstream.status, headers: outgoing });
  } catch {
    return Response.json({ detail: "Backend unavailable" }, { status: 503 });
  }
}

export { forward as GET, forward as POST, forward as PATCH, forward as PUT, forward as DELETE };
