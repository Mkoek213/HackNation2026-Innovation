// Contract types for GET /api/v1/knowledge/* (see backend OpenAPI).
import { api } from "@/features/workspace";

export type InnovationCard = { problem: string; solution: string; novelty: string; target_users: string; evidence: string };
export type InnovationDocument = { id: string; filename: string; content_type: string; download_url: string };
export type Author = { name: string; affiliation: string | null };
export const innovationAreas = { technologia: "Technologia", edukacja: "Edukacja", administracja: "Administracja" };
export type AssessmentNote = { basis: "potwierdzone" | "szacunek"; rationale: string; source_url: string | null; score: number | null };
export type Recipient = { audience: string; why: string };
export type Assessment = {
  implementation: AssessmentNote | null; novelty: AssessmentNote | null; transfer: AssessmentNote | null;
  credibility: AssessmentNote | null; trl: number | null; trl_basis: AssessmentNote | null; next_step: string;
  summary: string; recipients: Recipient[]; path: string | null; path_rationale: string; measures: string[];
  criteria_version: string; assessed_at: string | null;
};
export type Discovery = {
  area: keyof typeof innovationAreas | null; region: string | null; checked_at: string | null;
  verification: "potwierdzona" | "kandydat" | "zgloszone"; assessment: Assessment;
};
export type Innovation = {
  id: string; title: string; categories: string[]; primary_category: string;
  innovation_type: string | null; institution_type: string | null; institution: string | null;
  authors: Author[]; maturity: string | null; source_name: string | null; imported_at: string | null;
  source_url: string | null; video_url: string | null; card: InnovationCard; documents: InnovationDocument[];
} & Discovery;
export type Taxonomy = {
  sectors: Record<string, string>; innovation_types: Record<string, string>;
  institution_types: Record<string, string>; maturity: Record<string, string>;
  audiences: Record<string, string>; paths: Record<string, string>;
  criteria: Record<"implementation" | "trl" | "novelty" | "transfer" | "credibility", [string, string]>;
  criteria_version: string;
};

const knowledge = <T,>(path: string) => api<T>(`api/v1/knowledge/${path}`);
export const getInnovations = () => knowledge<Innovation[]>("innovations");
export const getTaxonomy = () => knowledge<Taxonomy>("taxonomy");
export const getCatalog = (params: string) =>
  knowledge<{ items: Innovation[]; total: number; regions: string[] }>(`catalog?${params}`);
