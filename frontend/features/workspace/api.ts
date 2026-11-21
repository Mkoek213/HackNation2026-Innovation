export type Evidence = { text: string; source_file: string | null; page_start: number | null; page_end: number | null; document_id: string | null; document_url: string | null; content_type: string | null };
export type Innovation = { id: string; title: string; solution: string; source_url: string | null; video_url: string | null; evidence: Evidence[]; fit_reason?: string | null; limitations?: string[] };
export type Artifact = { id: string; type: "idea_card" | "application_draft" | "adaptation_plan"; title: string; content_markdown: string; revision: number; updated_at: string };
export type SourceMetadata = { id: string; title: string; url?: string | null; publication_date?: string | null; geography?: string | null; source_file?: string | null; page_start?: number | null; page_end?: number | null };
export type MatterLink = { id: number; title: string; type: "idea_card" | "application_draft" | "adaptation_plan" | "note"; status: "draft" | "ready" | "sent"; revision: number };
export type CreatorState = { active: boolean; steps: { key: string; label: string; done: boolean }[]; matter_id: number | null };
export type Operation = { id: number; key: string; content: string; status: "processing" | "completed" | "failed"; result: { answer: string; innovations: Innovation[]; artifacts?: Artifact[]; sources?: SourceMetadata[]; matters?: MatterLink[]; creator?: CreatorState | null; suggestions?: string[]; outcome: "matched" | "no_match" | "unavailable" } | null };
export type Thread = { id: number; title: string | null; pending: boolean; last_activity_at: string };
export type Detail = Thread & { operations: Operation[] };
export type User = { id: number; username: string; role: "user" | "admin"; email: string | null };
export class ApiError extends Error { constructor(public status: number) { super("Request failed"); } }
let csrfCookie = "csrf_token";
let csrfHeader = "X-CSRF-Token";
async function request(path: string, method = "GET", body?: unknown, timeoutMs = 105000): Promise<Response> {
  // FormData sets its own multipart Content-Type with the boundary.
  const form = body instanceof FormData;
  const headers: Record<string, string> = form ? {} : { "Content-Type": "application/json" };
  if (method !== "GET" && !path.startsWith("auth/")) {
    // Refresh CSRF independently of JWT expiry; never replay the actual mutation.
    await session();
  }
  const token = document.cookie.split("; ").find((value) => value.startsWith(`${csrfCookie}=`))?.slice(csrfCookie.length + 1);
  if (token) headers[csrfHeader] = decodeURIComponent(token);
  const chatTurn = method === "POST" && /^workspace\/conversations\/\d+\/messages$/.test(path);
  const response = await fetch(`/api/backend/${path}`, { method, headers, credentials: "same-origin", cache: "no-store", body: body === undefined ? undefined : form ? body : JSON.stringify(body), signal: AbortSignal.timeout(chatTurn ? Math.max(timeoutMs, 690000) : timeoutMs) });
  if (!response.ok) throw new ApiError(response.status);
  return response;
}
export async function api<T>(path: string, method = "GET", body?: unknown, timeoutMs = 105000): Promise<T> {
  const response = await request(path, method, body, timeoutMs);
  if (response.status === 204 || !(response.headers.get("content-type") || "").includes("application/json")) return undefined as T;
  return response.json();
}
/** Download a PDF using the same authenticated request path as the workspace. */
export async function fetchPdf(path: string, method = "GET", body?: unknown): Promise<{ blob: Blob; filename: string | undefined }> {
  const response = await request(path, method, body);
  if (response.headers.get("content-type")?.split(";")[0].trim() !== "application/pdf") {
    throw new Error("PDF response expected");
  }
  const blob = await response.blob();
  if (await blob.slice(0, 5).text() !== "%PDF-") throw new Error("Invalid PDF response");
  const header = response.headers.get("content-disposition") || "";
  const match = /filename="?([^";]+)"?/i.exec(header);
  return { blob, filename: match?.[1] };
}
export async function download(path: string, fallbackName: string, method = "GET", body?: unknown) {
  const { blob, filename } = await fetchPdf(path, method, body);
  saveFile(blob, filename || fallbackName);
}
export function saveFile(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.hidden = true;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    // Browsers may consume the URL after click() returns. Keep it alive for the save.
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
}
export async function session() {
  const data = await api<{ user: User; csrf_cookie: string; csrf_header: string }>("auth/session");
  csrfCookie = data.csrf_cookie; csrfHeader = data.csrf_header;
  return data.user;
}
/**
 * POST to a public endpoint. Anonymous visitors have no session, so this must not go through api()'s session refresh;
 * a logged-in cookie session with an expired CSRF token gets 403 once, refreshes it and retries.
 */
export async function publicPost(path: string, body: unknown, init: { keepalive?: boolean } = {}): Promise<Response> {
  const post = () => {
    const token = document.cookie.split("; ").find((value) => value.startsWith(`${csrfCookie}=`))?.slice(csrfCookie.length + 1);
    return fetch(`/api/backend/${path}`, {
      method: "POST", credentials: "same-origin", cache: "no-store", keepalive: init.keepalive,
      headers: { "Content-Type": "application/json", ...(token ? { [csrfHeader]: decodeURIComponent(token) } : {}) },
      body: JSON.stringify(body), signal: AbortSignal.timeout(60000),
    });
  };
  const response = await post();
  if (response.status !== 403) return response;
  try { await session(); } catch { return response; } // Not a session problem (e.g. a rejected origin).
  return post();
}
export async function recordVisit(path: string) {
  try {
    await publicPost("visits", { path }, { keepalive: true });
  } catch {
    // Statistics must never disturb navigation.
  }
}
export const sessionEvent = "radar-session";
export function notifySession() { window.dispatchEvent(new Event(sessionEvent)); }
export function safeLink(url: string | null | undefined) {
  if (!url) return null;
  try { const parsed = new URL(url); return ["https:", "http:"].includes(parsed.protocol) ? parsed.href : null; } catch { return null; }
}
export function documentLink(evidence: Evidence) {
  return evidence.document_id && evidence.document_url && /^\/api\/v1\/knowledge\/innovations\/[a-z0-9-]+\/documents\/[a-f0-9]{32}$/.test(evidence.document_url)
    ? `/api/backend${evidence.document_url}` : null;
}
