import { api, download } from "@/features/workspace";

export type MatterType = "idea_card" | "application_draft" | "adaptation_plan" | "note";
export type MatterStatus = "draft" | "ready" | "sent";
export type MatterSummary = { id: number; title: string; type: MatterType; status: MatterStatus; revision: number; conversation_id: number | null; created_at: string; updated_at: string };
export type Matter = MatterSummary & { content_markdown: string };
export type MatterPage = { total: number; items: MatterSummary[] };

export const matterTypeLabels: Record<MatterType, string> = {
  idea_card: "Karta innowacji",
  application_draft: "Zgłoszenie do Radaru",
  adaptation_plan: "Plan wdrożenia",
  note: "Notatka",
};
export const matterStatusLabels: Record<MatterStatus, string> = { draft: "Szkic", ready: "Gotowa", sent: "Wysłana" };

export function formatMatterDate(value: string) {
  return new Date(value).toLocaleString("pl-PL", { dateStyle: "medium", timeStyle: "short" });
}

export const listMatters = (offset = 0, limit = 20) => api<MatterPage>(`matters?limit=${limit}&offset=${offset}`);
export const getMatter = (id: number) => api<Matter>(`matters/${id}`);
export const createMatter = (title: string, type: MatterType) => api<Matter>("matters", "POST", { title, type });
export const updateMatter = (id: number, change: { expected_revision: number; title?: string; status?: MatterStatus; content_markdown?: string }) =>
  api<Matter>(`matters/${id}`, "PATCH", change);
export const deleteMatter = (id: number) => api(`matters/${id}`, "DELETE");
export const matterThread = (id: number) => api<{ conversation_id: number }>(`matters/${id}/thread`, "POST");
export const downloadMatterPdf = (id: number, title: string) => download(`matters/${id}/pdf`, `${title}.pdf`);
