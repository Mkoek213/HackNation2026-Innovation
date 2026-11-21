import type { Metadata } from "next";
import { AnalyticsPage } from "@/features/administration";

export const metadata: Metadata = { title: "Analityka - Radar innowacji" };

export default function Page() {
  return <main id="main" tabIndex={-1} className="page page-wide"><AnalyticsPage /></main>;
}
