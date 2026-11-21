export type ApplicationStatus = "pending" | "approved" | "rejected";
export type ApplicationSource = "tester" | "admin";
export type TesterApplication = {
  id: number; innovation_id: string; innovation_title: string; status: ApplicationStatus; source: ApplicationSource;
  message: string | null; decided_at: string | null; created_at: string; updated_at: string;
};
export type TesterApplicationAdmin = TesterApplication & {
  user_id: number; email: string; phone: string; roles: string[]; interests: string[]; tags: { id: number; name: string }[];
};

/** Status text; the status is always shown as text, never by colour alone. */
export const applicationStatusLabels: Record<ApplicationStatus, string> = {
  pending: "Oczekuje na decyzję",
  approved: "Zatwierdzone",
  rejected: "Odrzucone",
};

export function formatApplicationDate(value: string) {
  return new Date(value).toLocaleDateString("pl-PL");
}
