// Contract types for GET /api/v1/knowledge/* (see backend OpenAPI).
import { api } from "@/features/workspace";

export type InnovationCard = { problem: string; solution: string; novelty: string; target_users: string; evidence: string };
export type InnovationDocument = { id: string; filename: string; content_type: string; download_url: string };
export type Author = { name: string; affiliation: string | null };
export type Innovation = {
  id: string; title: string; categories: string[]; primary_category: string;
  innovation_type: string | null; institution_type: string | null; institution: string | null;
  authors: Author[]; maturity: string | null; source_name: string | null; imported_at: string | null;
  source_url: string | null; video_url: string | null; card: InnovationCard; documents: InnovationDocument[];
};
export type Taxonomy = {
  sectors: Record<string, string>; innovation_types: Record<string, string>;
  institution_types: Record<string, string>; maturity: Record<string, string>;
};

const knowledge = <T,>(path: string) => api<T>(`api/v1/knowledge/${path}`);
export const getInnovations = () => knowledge<Innovation[]>("innovations");
export const getTaxonomy = () => knowledge<Taxonomy>("taxonomy");
