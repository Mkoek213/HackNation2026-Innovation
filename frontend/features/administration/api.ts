import { api } from "@/features/workspace";

export type Period = { from: string; to: string };
type Counts = { conversations: number; unique_people: number; no_answer: number };
export type Outcomes = { matched: number; no_match: number; unavailable: number };

export type SiteStats = {
  period: Period; visits: number; unique_visitors: number; conversations: number; registered_users: number;
  series: { date: string; visits: number; unique_visitors: number; conversations: number }[];
};
export type WorkspaceStats = {
  period: Period; threads: number; unique_users: number; operations: number;
  processing: number; completed: number; failed: number; outcomes: Outcomes;
  series: (Outcomes & { date: string; threads: number; operations: number })[];
};
export type TagStatsList = {
  period: Period; total: number;
  items: (Counts & { tag_id: number; name: string; subtags: (Counts & { subtag_id: number; name: string })[] })[];
};
export type TrendList = {
  period: Period; previous_period: Period; total: number;
  items: { tag_id: number; tag_name: string; subtag_id: number | null; subtag_name: string | null; current: number; previous: number; change: number; change_pct: number | null }[];
};
export type TagTimeline = {
  period: Period; previous_period: Period; window_days: number; step_days: number; total: number;
  dates: { date: string; current: boolean }[];
  items: { tag_id: number; name: string; unique_people: number; previous_people: number; change: number; change_pct: number | null; conversations: number; no_answer: number; points: number[] }[];
};
export type InnovationRankList = {
  period: Period; total: number;
  items: { innovation_id: string; title: string; unique_searchers: number; times_shown: number; opened: number }[];
};
export type Stats = { site: SiteStats; workspace: WorkspaceStats; tags: TagStatsList; trends: TrendList; timeline: TagTimeline; innovations: InnovationRankList };

export const rankingPageSize = 20;

export async function loadStats(period: Period): Promise<Stats> {
  const query = new URLSearchParams(period).toString();
  const [site, workspace, tags, trends, timeline, innovations] = await Promise.all([
    api<SiteStats>(`stats/site?${query}`),
    api<WorkspaceStats>(`stats/workspace?${query}`),
    api<TagStatsList>(`stats/tags?${query}`),
    api<TrendList>(`stats/trends?${query}`),
    api<TagTimeline>(`stats/tags/timeline?${query}`),
    api<InnovationRankList>(`stats/innovations?${query}&limit=${rankingPageSize}`),
  ]);
  return { site, workspace, tags, trends, timeline, innovations };
}
